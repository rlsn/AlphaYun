"""
Script for model evaluation and analysis
rlsn 2024
"""
import matplotlib.pyplot as plt
from tqdm import tqdm
import numpy as np
from src.model.env import YunEnv, Rule
from src.model.agent import Agent
import argparse, time, itertools
from scipy.linalg import schur

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_file', type=str, help="filename of the model", default="Qh.npy")
    parser.add_argument('--seed', type=int, help="set seed", default=None)
    parser.add_argument('--run', action='store_true', help="run example match with lastest moddel")
    parser.add_argument('-r', action='store_true', help="start match with random initial states")
    parser.add_argument('--stats', action='store_true', help="run state analysis")
    parser.add_argument('-s', type=int, help="grid size of the stats to display", default=None)
    parser.add_argument('--tour', action='store_true', help="run tournament")
    parser.add_argument('--selfplay', action='store_true', help="run self play")
    parser.add_argument('--Smax', type=int, help="max energy level of the game", default=5)
    parser.add_argument('--Amax', type=int, help="max attack level of the game", default=3)


    args = parser.parse_args()
    if args.seed:
        seed = args.seed
    else:
        seed = int(time.time())
    np.random.seed(seed)
    print("running with seed", seed)

    rule = Rule(n_max_energy=args.Smax, level=args.Amax, init_energy=1)

    env = YunEnv(rule=rule)

    model = np.load(args.model_file,allow_pickle=True).item()
    nash = model.get('nash')
    Pi = model.get('pi')
    print("model loaded from {}, size {}".format(args.model_file, Pi.shape))

    if args.run:
        P1 = Agent(nash, name='p1')

        P2 = Agent(nash, name='p2')

        observation, info = env.reset(seed=None, opponent=P2, train=args.r)
        print("Example match:")
        print(0, info)
        for i in range(1, 100):
            action = P1.step(observation, env.action_space.n)
            observation, reward, terminated, truncated, info = env.step(action)
            print(i, info)
            if terminated or truncated:
                break

    if args.stats:
        # some analysis at particular states
        Na = env.action_space.n
        grid_size = args.s if args.s is not None else rule.n_max_energy+1
        action_labels = ["C"]+[f"A{i+1}" for i in range(rule.level)]+[f"D{i+1}" for i in range(rule.level)]

        # state-action value grid
        fig, axs = plt.subplots(grid_size, grid_size, figsize=(10, 10))
        fig.suptitle("Behavioral Strategy @ appox. Nash Equilibrium")
        for S1 in range(grid_size):
            for S2 in range(grid_size):
                S = S1 * (env.rule.n_max_energy+1) + S2

                if len(nash.shape)==3:
                    mean = nash.mean(0)
                    std = nash.std(0)
                    axs[S1,S2].bar(np.arange(Na)+1,mean[S],yerr=std[S], alpha=0.5)
                else:
                    axs[S1,S2].bar(np.arange(Na)+1,nash[S], alpha=0.5)

                axs[S1,S2].text(Na//2+1, 0.5, f"({S1},{S2})",
                            ha="center", va="center", color="black", alpha=0.15, fontsize=20, weight='bold')
                axs[S1,S2].set_xticks(np.arange(nash.shape[-1])+1,action_labels)
                axs[S1,S2].set_ylim(0, 1) 
                axs[S1,S2].grid()
                
                if S1==grid_size-1:
                    axs[S1,S2].set_xlabel("A")
                else:
                    axs[S1, S2].xaxis.set_ticklabels([])
                if S2 == 0:
                    axs[S1, S2].set_ylabel("pi(a|s)")
                else:
                    axs[S1, S2].yaxis.set_ticklabels([])

        fig.tight_layout()
        plt.show()

    if args.tour:
        num_matches_per_pair = 200
        max_steps = 30
        num_models = 20
        random_start = args.r
        pi = Pi[:num_models]
        NP = pi.shape[0]
        R = np.zeros([NP, NP])
        ns = env.rule.n_max_energy + 1
        state_freq = np.zeros(env.observation_space.n)
        state_value = [list() for i in range(env.observation_space.n)]
        win_last_state_freq = np.zeros(env.observation_space.n)
        tot_matches = num_matches_per_pair * (1 + NP) * NP / 2
        print("running tournament, total matches: {}".format(tot_matches))

        for i in tqdm(range(NP), position=0):
            for j in tqdm(range(NP), position=1, leave=False):
                if j < i:
                    R[i, j] = -R[j, i]
                    continue
                for k in range(num_matches_per_pair):
                    P1 = Agent(pi[i], mode='prob')
                    P2 = Agent(pi[j], mode='prob')

                    observation, info = env.reset(opponent=P2, train=random_start)
                    Lt = [info]
                    for t in range(max_steps):
                        action = P1.step(observation, Amask=env.available_actions(observation))
                        observation, reward, terminated, truncated, info = env.step(action)
                        Lt.append(info)
                        state_freq[observation] += 1
                        if terminated:
                            R[i, j] += reward
                            obs_set = set([inf["observation"] for inf in Lt])
                            for obs in obs_set:
                                state_value[obs] += [reward]
                            if reward == 1:
                                win_last_state_freq[Lt[-2]["observation"]] += 1
                            break
                        if truncated:
                            break

        R /= num_matches_per_pair
        tot = R.sum(1, keepdims=True) / NP

        # schur decomp
        fig, ax = plt.subplots(figsize=(6, 6))
        T, Z = schur(R, output='complex')
        cm = plt.get_cmap("RdBu_r")
        ax.set_title("First 2 components by Schur decomposition")
        col = (tot.max() - tot) / (tot.max() - tot.min())
        ax.scatter(Z.real[:, 0], Z.real[:, 1], marker='o', c=cm([int(c * 255) for c in col]))
        fig.tight_layout()

        # evaluation matrix

        fig, ax = plt.subplots(figsize=(8, 8))
        im = ax.imshow(-R, cmap="RdBu_r")
        ax.set_title("Evaluation matrix")

        ax.set_xticklabels([])
        ax.set_yticklabels([])

        fig.tight_layout()

        # state visit
        state_freq = state_freq[:ns ** 2] / state_freq.sum()
        state_freq = state_freq.reshape(ns, ns)

        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(state_freq, cmap="Reds")
        ax.set_title("State visit frequency")
        ax.set_xticks(np.arange(ns), np.arange(ns))
        ax.set_xlabel("S2")
        ax.set_yticks(np.arange(ns), np.arange(ns))
        ax.set_ylabel("S1")
        for i in range(ns):
            for j in range(ns):
                text = ax.text(j, i, round(state_freq[i, j], 2),
                               ha="center", va="center", color="w")
        fig.tight_layout()

        # winner last state
        win_last_state_freq = win_last_state_freq[:ns ** 2] / win_last_state_freq.sum()
        win_last_state_freq = win_last_state_freq.reshape(ns, ns)

        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(win_last_state_freq, cmap="Reds")
        ax.set_title("Winner last state frequency")
        ax.set_xticks(np.arange(ns), np.arange(ns))
        ax.set_xlabel("S2")
        ax.set_yticks(np.arange(ns), np.arange(ns))
        ax.set_ylabel("S1")
        for i in range(ns):
            for j in range(ns):
                text = ax.text(j, i, round(win_last_state_freq[i, j], 2),
                               ha="center", va="center", color="w")
        fig.tight_layout()

        # V(s)
        state_value = np.array([np.mean(r) if len(r) > 0 else 0 for r in state_value])
        state_value = state_value[:ns ** 2]
        state_value = state_value.reshape(ns, ns)
        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(-state_value, cmap="RdBu_r")
        ax.set_title("State-value V(s) @ varying states")
        ax.set_xticks(np.arange(ns), np.arange(ns))
        ax.set_xlabel("S2")
        ax.set_yticks(np.arange(ns), np.arange(ns))
        ax.set_ylabel("S1")
        for i in range(ns):
            for j in range(ns):
                text = ax.text(j, i, round(state_value[i, j], 2),
                               ha="center", va="center", color="w")
        fig.tight_layout()

        # stats
        plt.show()

    if args.selfplay:
        N = 100000
        print(f"running selfplay (custom vs nash) {int(N)} times")
        custom_pi = np.copy(nash)
        custom_pi[7]=np.array([1,0,0,0,0,0,0])
        P1 = Agent(custom_pi, mode='prob')
        P2 = Agent(nash, mode='prob')
        rewards = []
        length = []
        ns = env.rule.n_max_energy + 1
        state_freq = np.zeros(env.observation_space.n)
        state_value = [list() for i in range(env.observation_space.n)]
        win_last_state_freq = np.zeros(env.observation_space.n)
        for i in tqdm(range(int(N))):
            observation, info = env.reset(opponent=P2, train=args.r)
            Lt = [info]
            for t in itertools.count():
                action = P1.step(observation, env.action_space.n)
                observation, reward, terminated, truncated, info = env.step(action)
                Lt.append(info)
                state_freq[observation] += 1
                if terminated:
                    rewards += [reward]
                    length += [env._i_step]
                    obs_set = set([inf["observation"] for inf in Lt])
                    for obs in obs_set:
                        state_value[obs] += [reward]
                    if reward == 1:
                        win_last_state_freq[Lt[-2]["observation"]] += 1
                    break
                if truncated:
                    length += [env._i_step]
                    break

        # state visit
        state_freq = state_freq[:ns ** 2] / state_freq.sum()
        state_freq = state_freq.reshape(ns, ns)

        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(state_freq, cmap="Reds")
        ax.set_title("State visit frequency")
        ax.set_xticks(np.arange(ns), np.arange(ns))
        ax.set_xlabel("S2")
        ax.set_yticks(np.arange(ns), np.arange(ns))
        ax.set_ylabel("S1")
        for i in range(ns):
            for j in range(ns):
                text = ax.text(j, i, round(state_freq[i, j], 2),
                               ha="center", va="center", color="w")
        fig.tight_layout()

        # winner last state
        win_last_state_freq = win_last_state_freq[:ns ** 2] / win_last_state_freq.sum()
        win_last_state_freq = win_last_state_freq.reshape(ns, ns)

        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(win_last_state_freq, cmap="Reds")
        ax.set_title("P1 Winning state frequency")
        ax.set_xticks(np.arange(ns), np.arange(ns))
        ax.set_xlabel("S2")
        ax.set_yticks(np.arange(ns), np.arange(ns))
        ax.set_ylabel("S1")
        for i in range(ns):
            for j in range(ns):
                text = ax.text(j, i, round(win_last_state_freq[i, j], 2),
                               ha="center", va="center", color="w")
        fig.tight_layout()

        # V(s)
        state_value = np.array([np.average(r) for r in state_value])
        state_value = state_value[:ns ** 2]
        state_value = state_value.reshape(ns, ns)
        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(-state_value, cmap="RdBu_r")
        ax.set_title("State-value V(s) @ varying states")
        ax.set_xticks(np.arange(ns), np.arange(ns))
        ax.set_xlabel("S2")
        ax.set_yticks(np.arange(ns), np.arange(ns))
        ax.set_ylabel("S1")
        for i in range(ns):
            for j in range(ns):
                text = ax.text(j, i, round(state_value[i, j], 2),
                               ha="center", va="center", color="w")
        fig.tight_layout()

        rewards = np.array(rewards)
        win = rewards[rewards > 0].shape[0]
        print(f"total match finished within {env.max_episode_steps} steps: {len(rewards)}")
        print(f"win/loss={win}/{len(rewards)-win}")
        print(f"mean length = {np.average(length)} +- {np.std(length)/np.sqrt(len(length))}")
        print(f"mean reward = {np.average(rewards)} +- {np.std(rewards)/np.sqrt(len(rewards))}")
        plt.show()
