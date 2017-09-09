import numpy as np
import tensorflow as tf
from utils import piecewise_linear_decay
from utils import ReplayBuffer, RingBuffer
from model import DQNModel
from base_agent import BaseAgent


# TODO: Better way to get history_length, maybe using state_shape
class DQNAgent(BaseAgent):
    def __init__(self, env, log_dir, history_length=4, graph=None, input_type=None, double=False):
        super(DQNAgent, self).__init__(env, log_dir)
        state_shape = np.squeeze(self.state).shape
        num_actions = env.action_space.n
        self.model = DQNModel(state_shape + (history_length,),
                              num_actions, graph, double=double)
        self.history_length = history_length
        self.replay_buffer = None

        # Keep track of past states
        self.states_history = RingBuffer(state_shape, history_length)

    def select_action(self, state, epsilon):
        # Select action based on an egreedy policy
        if np.random.random() <= epsilon:
            action = self.env.action_space.sample()
        else:
            Q_values = self.model.predict(self.sess, state[np.newaxis])
            action = np.argmax(Q_values)

        return action

    def play_one_life(self, epsilon=0.01, render=True):
        self._maybe_create_tf_sess()
        done = False
        while not done:
            if render:
                self.env.render()

            self.states_history.append(self.state)
            state = self.states_history.get_data()

            action = self.select_action(state, epsilon)
            next_state, reward, done, _ = env.step(action)

            if done:
                self.state = env.reset()
                self.states_history.reset()
            else:
                self.state = next_state

    #TODO: Define how pass lr_func, get_epsilon
    def train(self, num_steps, learning_rate, exploration_schedule, replay_buffer_size, target_update_freq, learning_freq=4, init_buffer_size=0.05, batch_size=32):
        '''
        Trains the agent following these steps:
            1. Use the current state to calculate Q-values
               and choose an action based on an epsilon-greedy policy
            2. Store experience on the replay buffer
            3. Every <learning_freq> steps sample the buffer
               and performs gradient descent

        Args:
            num_steps: Number of steps to train the agent
            learning_rate: Float or a function that returns a float
                           when called with the current time step as input
                           (see utils.linear_decay as an example)
            exploration_schedule: Function that returns a float when
                                  called with the current time step as input
                                  (see utils.linear_decay as an example)
            replay_buffer_size: Maximum number of transitions stored on replay buffer
            learning_freq: Number of steps between each gradient descent update
            init_buffer_size: Percentage of buffer filled with random transitions
                              before the training starts
        '''
        self._maybe_create_tf_sess()
        # Create replay buffer
        if self.replay_buffer is None:
            self.replay_buffer = ReplayBuffer(int(replay_buffer_size),
                                              self.history_length,
                                              batch_size)
            # Populate replay buffer with random agent
            num_init_replays = replay_buffer_size * init_buffer_size
            for i in range(int(num_init_replays)):
                self.states_history.append(self.state)
                state = self.states_history.get_data()

                action = self.env.action_space.sample()
                next_state, reward, done, _ = self.env.step(action)

                self.replay_buffer.add(self.state, action, reward, done)

                if done:
                    self.state = self.env.reset()
                    self.states_history.reset()
                else:
                    self.state = next_state

                if i % 100 == 0:
                    print('\rPopulating replay buffer: {:.1f}%'.format(
                        i * 100 / num_init_replays), end='', flush=True)

        reward_sum = 0
        self.model.update_target_net(self.sess)
        for i_step in range(int(num_steps)):
            self.states_history.append(self.state)
            state = self.states_history.get_data()

            # Play one step based on a epsilon greedy policy
            epsilon = exploration_schedule(i_step)
            action = self.select_action(state, epsilon)

            next_state, reward, done, _ = self.env.step(action)
            reward_sum += reward

            # Store experience
            self.replay_buffer.add(self.state, action, reward, done)

            # Update state
            if done:
                self.state = self.env.reset()
                self.states_history.reset()
            else:
                self.state = next_state

            # Perform gradient descent
            if i_step % learning_freq == 0:
                # Sample replay buffer
                b_s, b_s_, b_a, b_r, b_d = self.replay_buffer.sample()
                # Calculate learning rate
                if callable(learning_rate):
                    lr = learning_rate(i_step)
                else:
                    lr = learning_rate
                self.model.train(self.sess, lr, b_s, b_s_, b_a, b_r, b_d)

            # Update target network
            if i_step % target_update_freq == 0:
                self.model.update_target_net(self.sess)

            if done:
                print(reward_sum)
                reward_sum = 0