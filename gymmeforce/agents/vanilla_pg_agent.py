import numpy as np

from gymmeforce.agents import BatchAgent
from gymmeforce.common.utils import discounted_sum_rewards, explained_variance
from gymmeforce.models import VanillaPGModel


class VanillaPGAgent(BatchAgent):
    '''
    Vanilla Policy Gradient

    Args:
    	env_name: Gym environment name

    Keyword args:
        normalize_advantages: Whether or not to normalize advantages (default False)
        use_baseline: Whether or not to subtract a baseline(NN representing the
            value function) from the returns (default True)
        entropy_coef: Entropy penalty added to the loss (default 0.0)
        policy_graph: Function returning a tensorflow graph representing the policy
            (default None)
        value_graph: Function returning a tensorflow graph representing the value function
            (default None)
        log_dir: Directory used for writing logs (default 'logs/examples')
    '''

    def __init__(self, env_name, normalize_advantages=False, **kwargs):
        super(VanillaPGAgent, self).__init__(env_name, **kwargs)
        self.model = self._create_model(**kwargs)
        self.normalize_advantages = normalize_advantages

    def _create_model(self, **kwargs):
        return VanillaPGModel(self.env_config, **kwargs)

    def _add_discounted_returns(self, trajectory):
        discounted_returns = discounted_sum_rewards(trajectory['rewards'], self.gamma)
        trajectory['returns'] = discounted_returns

    def _add_advantages_and_vtarget(self, trajectory):
        if self.model.use_baseline:
            # This is the classical way to fit vtarget (directly by the return)
            # TODO: Should a option to bootstrap be added?
            trajectory['baseline_target'] = trajectory['returns']
            trajectory['baseline'] = self.model.compute_baseline(
                self.sess, trajectory['states'])
            trajectory['advantages'] = trajectory['returns'] - trajectory['baseline']
        else:
            trajectory['advantages'] = trajectory['returns']

    def _normalize_advantages(self, batch):
        mean_adv = np.mean(batch['advantages'])
        std_adv = np.std(batch['advantages'])
        batch['advantages'] = (batch['advantages'] - mean_adv) / (std_adv + 1e-7)

    def select_action(self, state):
        action = self.model.select_action(self.sess, state)
        if self.env_config['action_space'] == 'continuous':
            action = action[0]

        return action

    def generate_batch(self, **kwargs):
        trajectories = self.generate_trajectories(**kwargs)
        for trajectory in trajectories:
            self._add_discounted_returns(trajectory)
            self._add_advantages_and_vtarget(trajectory)

        self.batch = {
            'states':
            np.concatenate([traj['states'] for traj in trajectories]),
            'actions':
            np.concatenate([traj['actions'] for traj in trajectories]),
            'rewards':
            np.concatenate([traj['rewards'] for traj in trajectories]),
            'returns':
            np.concatenate([traj['returns'] for traj in trajectories]),
            'advantages':
            np.concatenate([traj['advantages'] for traj in trajectories]),
            # Change to vtarg
            'baseline':
            np.concatenate([traj['baseline'] for traj in trajectories]),
            'baseline_targets':
            np.concatenate([traj['baseline_target'] for traj in trajectories])
        }

        if self.normalize_advantages:
            self._normalize_advantages(self.batch)

    def write_logs(self, batch):
        super().write_logs(batch)

        ev = explained_variance(
            y_true=batch['baseline_targets'], y_pred=batch['baseline'])
        self.logger.add_log('baseline/Explained Variance', ev)

        self.logger.log('Iter {} | Episode {} | Step {}'.format(
            self.i_iter, self.i_episode, self.i_step))

    def train(self, learning_rate, gamma=0.99, **kwargs):
        self.learning_rate = learning_rate
        self.gamma = gamma
        super().train(**kwargs)

        while True:
            # Generate policy rollouts
            self.generate_batch(ep_runner=self.train_ep_runner, **kwargs)

            lr = self._calculate_schedule(self.learning_rate)
            self.model.fit(sess=self.sess, batch=self.batch, learning_rate=lr, **kwargs)

            self.write_logs(self.batch)

            if self._step_and_check_termination():
                break

        # Save
        self.save()
