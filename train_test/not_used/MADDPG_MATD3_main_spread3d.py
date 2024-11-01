import torch
import numpy as np
from torch.utils.tensorboard import SummaryWriter
from env.make_env import make_env
import argparse
from train_test.utils.replay_buffer import ReplayBuffer
from train_test.utils.maddpg import MADDPG
from train_test.utils.matd3 import MATD3
import copy
from gym_pybullet_drones.envs.Spread3d import Spread3dAviary
from gym_pybullet_drones.utils.enums import ObservationType, ActionType

Env_name = 'spread3d'   # 'spread3d', 'simple_spread'
action = 'vel'


class Runner:
    def __init__(self, args):
        self.args = args
        self.args.decive = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.env_name = Env_name
        self.number = args.N_drones
        self.seed = 1145  # 保证一个seed，名称使用记号--mark
        self.mark = args.mark
        self.args.share_prob = 0.05    # 还是别共享了，有些无用
        # Create env
        if self.env_name == 'spread3d':
            Ctrl_Freq = args.Ctrl_Freq  # 30
            self.env = Spread3dAviary(gui=True, num_drones=args.N_drones, obs=ObservationType('kin_target'),
                                      act=ActionType(action),
                                      ctrl_freq=Ctrl_Freq,  # 这个值越大，仿真看起来越慢，应该是由于频率变高，速度调整的更小了
                                      need_target=True, obs_with_act=True)
            # self.env_evaluate = Spread3dAviary(gui=False, num_drones=args.N_drones, obs=ObservationType('kin_target'),
            #                                    act=ActionType(action),
            #                                    ctrl_freq=Ctrl_Freq,
            #                                    need_target=True, obs_with_act=True)
            self.timestep = 1 / Ctrl_Freq  # 计算每个步骤的时间间隔 0.003

            # self.env.observation_space.shape = box[N,78]
            self.args.obs_dim_n = [self.env.observation_space[i].shape[0] for i in
                                   range(self.args.N_drones)]  # obs dimensions of N agents
            self.args.action_dim_n = [self.env.action_space[i].shape[0] for i in
                                      range(self.args.N_drones)]  # actions dimensions of N agents
            # print("observation_space=", self.env.observation_space)
            print("obs_dim_n={}".format(self.args.obs_dim_n))
            # print("action_space=", self.env.action_space)
            print("action_dim_n={}".format(self.args.action_dim_n))
        elif self.env_name == 'simple_spread':
            self.env = make_env(self.env_name, Discrete=False)  # Continuous action space
            self.env_evaluate = make_env(self.env_name, Discrete=False)
            self.args.N = self.env.n  # The number of agents
            self.args.obs_dim_n = [self.env.observation_space[i].shape[0] for i in
                                   range(self.args.N)]  # obs dimensions of N agents
            self.args.action_dim_n = [self.env.action_space[i].shape[0] for i in
                                      range(self.args.N)]  # actions dimensions of N agents
            print("observation_space=", self.env.observation_space)
            print("obs_dim_n={}".format(self.args.obs_dim_n))
            print("action_space=", self.env.action_space)
            print("action_dim_n={}".format(self.args.action_dim_n))

        # Set random seed
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)

        # Create N agents
        if self.args.algorithm == "MADDPG":
            print("Algorithm: MADDPG")
            self.agent_n = [MADDPG(args, agent_id) for agent_id in range(args.N_drones)]
        elif self.args.algorithm == "MATD3":
            print("Algorithm: MATD3")
            self.agent_n = MATD3.initialize_agents(args)
        else:
            print("Wrong!!!")
        self.replay_buffer = ReplayBuffer(self.args)

        # Create a tensorboard
        self.writer = SummaryWriter(
            log_dir='runs/{}/{}_env_{}_number_{}_mark_{}'.format(self.args.algorithm, self.args.algorithm,
                                                                 self.env_name, self.number, self.mark))

        self.evaluate_rewards = []  # Record the rewards during the evaluating
        self.total_steps = 0
        self.noise_std = self.args.noise_std_init  # Initialize noise_std

    def convert_obs_dict_to_array(self, obs_dict):
        obs_array = []
        if self.args.N_drones != 1:
            for i in range(self.args.N_drones):
                obs = obs_dict[i]
                # action_buffer_flat = np.hstack(obs['action_buffer'])    # 拉成一维
                obs_array.append(np.hstack([
                    obs['pos'],
                    obs['rpy'],
                    obs['vel'],
                    obs['ang_vel'],
                    obs['target_pos'],
                    obs['other_pos'],
                    obs['action_buffer']    # 先不考虑动作
                ]))
        else:
            pass
        return np.array(obs_array).astype('float32')

    def convert_wrap(self, obs_dict):
        if self.env_name == 'spread3d':   # 'simple_spread'
            if isinstance(obs_dict, dict):
                obs_dict = self.convert_obs_dict_to_array(obs_dict)
            else:
                obs_dict = obs_dict
            return obs_dict
        elif self.env_name == 'simple_spread':
            return obs_dict

    def run(self, ):
        while self.total_steps < self.args.max_train_steps:
            if self.env_name == 'spread3d':
                obs_n, _ = self.env.reset()  # gym new api
            else:
                obs_n = self.env.reset()  # gym old api
            obs_n = self.convert_wrap(obs_n)
            train_reward = 0
            rewards_n = [0] * self.args.N_drones

            for count in range(self.args.episode_limit):

                a_n = [agent.choose_action(obs, noise_std=self.noise_std) for agent, obs in zip(self.agent_n, obs_n)]
                # print(f'a_n:{a_n}')
                if self.env_name == 'spread3d':
                    obs_next_n, r_n, done_n, _, _ = self.env.step(copy.deepcopy(a_n))  # gym new api
                else:
                    obs_next_n, r_n, done_n, _ = self.env.step(copy.deepcopy(a_n))
                obs_next_n = self.convert_wrap(obs_next_n)

                self.replay_buffer.store_transition(obs_n, a_n, r_n, obs_next_n, done_n)
                obs_n = obs_next_n
                train_reward += np.mean(r_n)
                rewards_n = [r + reward for r, reward in zip(rewards_n, r_n)]  # Accumulate rewards for each agent
                self.total_steps += 1

                if self.args.use_noise_decay:
                    self.noise_std = self.noise_std - self.args.noise_std_decay if self.noise_std - self.args.noise_std_decay > self.args.noise_std_min else self.args.noise_std_min

                # 之前这里还可以拓展，现在不行了，在仿真中用掉了时间

                if self.total_steps % self.args.evaluate_freq == 0:
                    # self.evaluate_policy()
                    self.save_model()  # 评估中实现save了
                    if self.env_name == 'spread3d':
                        obs_n, _ = self.env.reset()  # gym new api
                    else:
                        obs_n = self.env.reset()  # gym old api
                    obs_n = self.convert_wrap(obs_n)

                if all(done_n):
                    break

            if self.replay_buffer.current_size > self.args.batch_size:
                for _ in range(50):
                    for agent_id in range(self.args.N_drones):
                        self.agent_n[agent_id].train(self.replay_buffer, self.agent_n)

            print("total_steps:{} \t train_reward:{} \t noise_std:{}".format(self.total_steps, train_reward,
                                                                             self.noise_std))

            for agent_id, reward in enumerate(rewards_n):
                self.writer.add_scalar('Agent_{}_train_reward'.format(agent_id), reward, global_step=self.total_steps)

            self.writer.add_scalar('train_step_rewards_{}'.format(self.env_name), train_reward,
                                   global_step=self.total_steps)

        self.env.close()
        # self.env_evaluate.close()

    def evaluate_policy(self, ):
        evaluate_reward = 0
        for _ in range(self.args.evaluate_times):
            obs_n, _ = self.env_evaluate.reset()
            episode_reward = 0
            a = self.agent_n[0].choose_action(obs_n[0], 0)
            for _ in range(self.args.test_episode_limit):

                a_n = [agent.choose_action(obs, noise_std=0) for agent, obs in
                       zip(self.agent_n, obs_n)]  # We do not add noise when evaluating
                obs_next_n, r_n, done_n, _, _ = self.env_evaluate.step(copy.deepcopy(a_n))
                episode_reward += np.mean(r_n)  # 修改为均值
                obs_n = obs_next_n

                if all(done_n):
                    break
            evaluate_reward += episode_reward

        evaluate_reward = evaluate_reward / self.args.evaluate_times
        self.evaluate_rewards.append(evaluate_reward)
        # print("total_steps:{} \t evaluate_reward:{} \t noise_std:{}".format(self.total_steps, evaluate_reward,
        #                                                                     self.noise_std))
        # self.writer.add_scalar('evaluate_step_rewards_{}'.format(self.env_name), evaluate_reward,
        #                        global_step=self.total_steps)
        # Save the rewards and models
        # np.save('./data_train/{}_env_{}_number_{}_seed_{}.npy'.format(self.args.algorithm, self.env_name, self.number,
        #                                                               self.seed), np.array(self.evaluate_rewards))
        for agent_id in range(self.args.N_drones):
            self.agent_n[agent_id].save_model(self.env_name, self.args.algorithm, self.mark, self.number, self.total_steps,
                                              agent_id)

    def save_model(self):
        for agent_id in range(self.args.N_drones):
            self.agent_n[agent_id].save_model(self.env_name, self.args.algorithm, self.mark, self.number, self.total_steps,
                                              agent_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser("Hyperparameters Setting for MADDPG and MATD3 in MPE environment")
    parser.add_argument("--max_train_steps", type=int, default=int(1e6), help=" Maximum number of training steps")
    parser.add_argument("--episode_limit", type=int, default=1000, help="Maximum number of steps per episode")
    parser.add_argument("--test_episode_limit", type=int, default=1000, help="Maximum number of steps per test episode")
    parser.add_argument("--evaluate_freq", type=float, default=100000,
                        help="Evaluate the policy every 'evaluate_freq' steps")
    parser.add_argument("--evaluate_times", type=float, default=1, help="Evaluate times")
    parser.add_argument("--max_action", type=float, default=1.0, help="Max action")

    parser.add_argument("--algorithm", type=str, default="MATD3", help="MADDPG or MATD3")
    parser.add_argument("--buffer_size", type=int, default=int(1e6), help="The capacity of the replay buffer")
    parser.add_argument("--batch_size", type=int, default=1024, help="Batch size")  # 1024-》4048
    parser.add_argument("--hidden_dim", type=int, default=64,
                        help="The number of neurons in hidden layers of the neural network")
    parser.add_argument("--noise_std_init", type=float, default=0.02, help="The std of Gaussian noise for exploration")
    parser.add_argument("--noise_std_min", type=float, default=0.005, help="The std of Gaussian noise for exploration")
    parser.add_argument("--noise_decay_steps", type=float, default=3e5,
                        help="How many steps before the noise_std decays to the minimum")
    parser.add_argument("--use_noise_decay", type=bool, default=True, help="Whether to decay the noise_std")
    parser.add_argument("--lr_a", type=float, default=5e-4, help="Learning rate of actor")
    parser.add_argument("--lr_c", type=float, default=5e-4, help="Learning rate of critic")
    parser.add_argument("--gamma", type=float, default=0.99, help="Discount factor")
    parser.add_argument("--tau", type=float, default=0.01, help="Softly update the target network")
    parser.add_argument("--use_orthogonal_init", type=bool, default=True, help="Orthogonal initialization")
    parser.add_argument("--use_grad_clip", type=bool, default=True, help="Gradient clip")
    parser.add_argument("--device", type=str, default="cpu", help="Device to train model")
    # --------------------------------------MATD3--------------------------------------------------------------------
    parser.add_argument("--policy_noise", type=float, default=0.2, help="Target policy smoothing")
    parser.add_argument("--noise_clip", type=float, default=0.5, help="Clip noise")
    parser.add_argument("--policy_update_freq", type=int, default=2, help="The frequency of policy updates")

    parser.add_argument("--mark", type=int, default=1145, help="The frequency of policy updates")
    parser.add_argument("--N_drones", type=int, default=3, help="The number of drones")
    parser.add_argument("--Ctrl_Freq", type=int, default=30, help="The frequency of ctrl")
    args = parser.parse_args()
    args.noise_std_decay = (args.noise_std_init - args.noise_std_min) / args.noise_decay_steps

    runner = Runner(args)
    runner.run()
