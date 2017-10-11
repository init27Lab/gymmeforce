import os
import gym
import numpy as np
import tensorflow as tf
import itertools
from gymmeforce.agents import BatchAgent
# from gymmeforce.models.vanilla_pg_model2 import VanillaPGModel
from gymmeforce.models.vanilla_pg_model import VanillaPGModel

class VanillaPGAgent(BatchAgent):
    def __init__(self, env_name, log_dir, normalize_advantages=False, use_baseline=True, normalize_baseline=True, entropy_coef=0.,
                 policy_graph=None, value_graph=None, input_type=None, env_wrapper=None, debug=False):
        super(VanillaPGAgent, self).__init__(env_name, log_dir, env_wrapper=env_wrapper, debug=debug)
        self.normalize_advantages = normalize_advantages
        self.use_baseline = use_baseline
        self.normalize_baseline = normalize_baseline
        # TODO: IF pg1 pass arguments here
        self.model = VanillaPGModel(self.env_config,
                                    use_baseline=use_baseline,
                                    entropy_coef=entropy_coef,
                                    # policy_graph=policy_graph,
                                    # value_graph=value_graph,
                                    log_dir=log_dir)

    def select_action(self, state):
        return self.model.select_action(self.sess, state)

    def train(self, learning_rate, max_iters=-1, max_episodes=-1, max_steps=-1, rew_discount_factor=0.99, timesteps_per_batch=2000, num_epochs=10, batch_size=64):
        self._maybe_create_tf_sess()
        monitored_env, env = self._create_env(os.path.join(self.log_dir, 'videos/train'))

        i_step = 0
        for i_iter in itertools.count():
            # Generate policy rollouts
            trajectories = self.generate_batch(env, timesteps_per_batch, gamma=rew_discount_factor)
            states = np.concatenate([trajectory['states'] for trajectory in trajectories])
            actions = np.concatenate([trajectory['actions'] for trajectory in trajectories])
            rewards = np.concatenate([trajectory['rewards'] for trajectory in trajectories])
            returns = np.concatenate([trajectory['returns'] for trajectory in trajectories])

            baseline_targets = returns
            if self.use_baseline:
                baseline = self.model.compute_baseline(self.sess, states)
                if self.normalize_baseline:
                    returns_mean = np.mean(returns)
                    returns_std = np.std(returns)
                    # Normalize targets
                    baseline_targets = (returns - returns_mean) / (returns_std + 1e-8)
                    # If baseline targets are normalized they have to be rescaled
                    # before subtracting from returns
                    baseline_mean = np.mean(baseline)
                    baseline_std = np.std(baseline)
                    norm_baseline = (baseline - baseline_mean) / (baseline_std + 1e-8)
                    baseline = norm_baseline * returns_std + returns_mean
                advantages = returns - baseline
            else:
                advantages = returns
            if self.normalize_advantages:
                advantages_mean = np.mean(advantages)
                advantages_std = np.std(advantages)
                advantages = (advantages - advantages_mean) / (advantages_std + 1e-8)

            # Train
            # self.model.fit(self.sess, states, actions, baseline_targets, advantages, num_epochs, batch_size, learning_rate, logger=self.logger)

            self.model.fit(self.sess, states, actions, returns, learning_rate, num_epochs, batch_size, logger=self.logger)

            # Logs
            ep_rewards = monitored_env.get_episode_rewards()
            i_episode = len(ep_rewards)
            num_episodes = len(trajectories)
            num_steps = len(rewards)
            i_step += num_steps
            self.logger.add_log('Reward Mean [{} episodes]'.format(num_episodes),
                                np.mean(ep_rewards[-num_episodes:]))
            self.logger.timeit(num_steps)
            self.logger.log('Iter {} | Episode {} | Step {}'.format(i_iter, i_episode, i_step))

            # Check for termination
            if (i_iter // max_iters >= 1
                or i_episode // max_episodes >= 1
                or i_step // max_steps >= 1):
                break