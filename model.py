import numpy as np
import tensorflow as tf
from utils import huber_loss


# TODO: Choice of loss (Huber or MSE)
class DQN:
    def __init__(self, state_shape, num_actions, clip_norm, gamma=0.99, double=False):
        self.state_shape = state_shape
        self.num_actions = num_actions
        self.double = double
        self.global_step_tensor = tf.Variable(1, name='global_step', trainable=False)

        if len(state_shape) == 3:
            state_type = tf.uint8
        elif len(state_shape) == 1:
            state_type = tf.float32
        else:
            raise ValueError('state_shape not supported: {}'.format(state_shape))

        # Model inputs
        self.states_t = tf.placeholder(
            name='states',
            shape=[None] + list(self.state_shape),
            dtype=state_type
        )
        self.states_tp1 = tf.placeholder(
            name='states_tp1',
            shape=[None] + list(self.state_shape),
            dtype=state_type
        )
        self.actions = tf.placeholder(
            name='actions',
            shape=[None],
            dtype=tf.int32
        )
        self.rewards = tf.placeholder(
            name='rewards',
            shape=[None],
            dtype=tf.float32
        )
        self.done_mask = tf.placeholder(
            name='done_mask',
            shape=[None],
            dtype=tf.float32
        )
        self.learning_rate_ph = tf.placeholder(
            name='learning_rate_ph',
            shape=[],
            dtype=tf.float32
        )
        self.global_step_ph = tf.placeholder(
            name='global_step_ph',
            shape=[],
            dtype=tf.int32
        )

        self.set_global_step_op = tf.assign(self.global_step_tensor,
                                            self.global_step_ph,
                                            name='step_global_step')
        self.increase_global_step_op = tf.assign(self.global_step_tensor,
                                                 self.global_step_tensor + 1,
                                                 name='increase_global_step')
        # Create model
        if len(state_shape) == 3:
            # Convert to float on GPU
            states_t_float = tf.cast(self.states_t, tf.float32) / 255.
            states_tp1_float = tf.cast(self.states_tp1, tf.float32) / 255.
            self.q_values = self._build_deepmind_model(states_t_float, 'online')
            self.q_target = self._build_deepmind_model(states_tp1_float, 'target')
            if double:
                self.q_values_tp1 = self._build_deepmind_model(states_tp1_float, 'online', reuse=True)

        elif len(state_shape) == 1:
            self.q_values = self._build_dense_model(self.states_t, 'online')
            self.q_target = self._build_dense_model(self.states_tp1, 'target')
            if double:
                self.q_values_tp1 = self._build_dense_model(self.states_tp1, 'online', reuse=True)

        # Create training operation
        self.training_op = self._build_optimization(clip_norm, gamma)
        self.update_target_op = self._build_target_update_op()

        # Create collections for loading later
        tf.add_to_collection('state_input', self.states_t)
        tf.add_to_collection('q_values', self.q_values)

    def _build_deepmind_model(self, states, scope, reuse=None):
        ''' Network model from DeepMind '''
        with tf.variable_scope(scope, reuse=reuse):
            # Model architecture
            net = states
            # Convolutional layers
            net = tf.layers.conv2d(net, 32, (8, 8), strides=(4, 4), activation=tf.nn.relu)
            net = tf.layers.conv2d(net, 64, (4, 4), strides=(2, 2), activation=tf.nn.relu)
            net = tf.layers.conv2d(net, 32, (3, 3), strides=(1, 1), activation=tf.nn.relu)
            net = tf.contrib.layers.flatten(net)

            # Dense layers
            net = tf.layers.dense(net, 512, activation=tf.nn.relu)
            output = tf.layers.dense(net, self.num_actions, name='Q_{}'.format(scope))

            return output

    def _build_dense_model(self, states, scope, reuse=None):
        ''' Simple fully connected model '''
        with tf.variable_scope(scope, reuse=reuse):
            # Model architecture
            net = states
            net = tf.layers.dense(net, 512, activation=tf.nn.relu)
            output = tf.layers.dense(net, self.num_actions, name='Q_{}'.format(scope))

            return output

    def _build_optimization(self, clip_norm, gamma):
        # Choose only the q values for selected actions
        onehot_actions = tf.one_hot(self.actions, self.num_actions)
        q_t = tf.reduce_sum(tf.multiply(self.q_values, onehot_actions), axis=1)

        # Caculate td_target
        if self.double:
            best_actions_onehot = tf.one_hot(tf.argmax(self.q_values_tp1, axis=1), self.num_actions)
            q_tp1 = tf.reduce_sum(tf.multiply(self.q_target, best_actions_onehot), axis=1)
        else:
            q_tp1 = tf.reduce_max(self.q_target, axis=1)
        td_target = self.rewards + (1 - self.done_mask) * gamma * q_tp1
        # errors = tf.squared_difference(q_t, td_target)
        errors = huber_loss(q_t, td_target)
        self.total_error = tf.reduce_mean(errors)

        # Create training operation
        opt = tf.train.AdamOptimizer(self.learning_rate_ph, epsilon=1e-4)
        # Clip gradients
        online_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='online')
        grads_and_vars = opt.compute_gradients(self.total_error, online_vars)
        clipped_grads = [(tf.clip_by_norm(grad, clip_norm), var)
                         for grad, var in grads_and_vars if grad is not None]
        training_op = opt.apply_gradients(clipped_grads)

        return training_op

    def _build_target_update_op(self, alpha=1):
        # Get variables within defined scope
        online_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'online')
        target_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, 'target')
        # Create operations that copy the variables
        op_holder = [target_var.assign(alpha * online_var + (1 - alpha) * target_var)
                     for online_var, target_var in zip(online_vars, target_vars)]

        return op_holder

    def predict(self, sess, states):
        return sess.run(self.q_values, feed_dict={self.states_t: states})

    def target_predict(self, sess, states):
        return sess.run(self.q_target, feed_dict={self.states_tp1: states})

    def train(self, sess, learning_rate, states_t, states_tp1, actions, rewards, dones):
        feed_dict = {
            self.learning_rate_ph: learning_rate,
            self.states_t: states_t,
            self.states_tp1: states_tp1,
            self.actions: actions,
            self.rewards: rewards,
            self.done_mask: dones
        }
        sess.run(self.training_op, feed_dict=feed_dict)

    def update_target_net(self, sess):
        sess.run(self.update_target_op)

    # TODO: Maybe integrate summary writing in self.train
    def create_summaries(self):
        tf.summary.scalar('loss', self.total_error)
        tf.summary.scalar('Q_mean', tf.reduce_mean(self.q_values))
        tf.summary.scalar('Q_max', tf.reduce_max(self.q_values))
        tf.summary.histogram('Q_values', self.q_values)
        merged = tf.summary.merge_all()

        def run_op(sess, sv, states_t, states_tp1, actions, rewards, dones):
            feed_dict = {
                self.states_t: states_t,
                self.states_tp1: states_tp1,
                self.actions: actions,
                self.rewards: rewards,
                self.done_mask: dones
            }
            summary = sess.run(merged, feed_dict=feed_dict)
            sv.summary_computed(sess, summary)

        return run_op

    def summary_scalar(self, sess, sv, name, value):
        summary = tf.Summary(value=[
            tf.Summary.Value(tag=name, simple_value=value),
        ])
        sv.summary_computed(sess, summary)

    def increase_global_step(self, sess):
        # Increasing the global step every timestep was consuming too much time
        sess.run(self.increase_global_step_op)

    def set_global_step(self, sess, step):
        sess.run(self.set_global_step_op, feed_dict={self.global_step_ph: step})

    def initialize(self, sess):
        sess.run(tf.global_variables_initializer())
