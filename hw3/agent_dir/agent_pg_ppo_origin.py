# -*- coding: utf-8 -*-
"""
Created on Tue May  7 12:22:44 2019

@author: hb2506
"""

import torch
import torch.nn as nn
from torch.distributions import Categorical
import numpy as np
from agent_dir.agent import Agent
import gym

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

class PolicyNet(nn.Module):
    def __init__(self, state_dim, action_num, hidden_dim):
        super(PolicyNet, self).__init__()
        self.affine = nn.Linear(state_dim, hidden_dim)
        
        # actor
        self.action_layer = nn.Sequential(
                nn.Linear(state_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, action_num),
                nn.Softmax()
                )
        
        # critic
        self.value_layer = nn.Sequential(
                nn.Linear(state_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, 1)
                )
        
        # Memory:
        self.actions = []
        self.states = []
        self.logprobs = []
        self.state_values = []
        self.rewards = []
        
    def forward(self, state, action=None, evaluate=False):
        # if evaluate is True then we also need to pass an action for evaluation
        # else we return a new action from distribution
        if not evaluate:
            state = torch.from_numpy(state).float().to(device)
        
        state_value = self.value_layer(state)
        
        action_probs = self.action_layer(state)
        action_distribution = Categorical(action_probs)
        
        if not evaluate:
            action = action_distribution.sample()
            self.actions.append(action)
            
        self.logprobs.append(action_distribution.log_prob(action))
        self.state_values.append(state_value)
        
        if evaluate:
            return action_distribution.entropy().mean()
        
        if not evaluate:
            return action.item()
        
    def clearMemory(self):
        del self.actions[:]
        del self.states[:]
        del self.logprobs[:]
        del self.state_values[:]
        del self.rewards[:]
        
class AgentPG(Agent):
    def __init__(self, env, args):
        self.env = env
        env.seed(9487)
        self.lr = 1e-3
        self.betas = (0.9, 0.999)
        self.gamma = 0.99
        self.eps_clip = 0.2
        self.display_freq = 10
        self.eps = np.finfo(np.float32).eps.item()
        self.K_epochs = 10
        self.num_episodes = 10000
        self.n_update = 1
        
        self.policy = PolicyNet(state_dim = self.env.observation_space.shape[0],
                               action_num= self.env.action_space.n,
                               hidden_dim=64).to(device)
        self.optimizer = torch.optim.Adam(self.policy.parameters(),
                                              lr=self.lr, betas=self.betas)
        self.policy_old = PolicyNet(state_dim = self.env.observation_space.shape[0],
                               action_num= self.env.action_space.n,
                               hidden_dim=64).to(device)
        
        self.MseLoss = nn.MSELoss()
    
#    def init_game_setting(self):
#        self.rewards = []
#        self.saved_actions = []
#        self.saved_log_probs = []
        
    def update(self):   
        # Monte Carlo estimate of state rewards:
        rewards = []
        discounted_reward = 0
        for reward in reversed(self.policy_old.rewards):
            discounted_reward = reward + (self.gamma * discounted_reward)
            rewards.insert(0, discounted_reward)
        
        # Normalizing the rewards:
        rewards = torch.tensor(rewards).to(device)
        rewards = (rewards - rewards.mean()) / (rewards.std() + 1e-5)
        
        # convert list in tensor
        old_states = torch.tensor(self.policy_old.states).to(device).detach()
        old_actions = torch.tensor(self.policy_old.actions).to(device).detach()
        old_logprobs = torch.tensor(self.policy_old.logprobs).to(device).detach()
        
        # Optimize policy for K epochs:
        for _ in range(self.K_epochs):
            # Evaluating old actions and values :
            dist_entropy = self.policy(old_states, old_actions, evaluate=True)
            
            # Finding the ratio (pi_theta / pi_theta__old):
            logprobs = self.policy.logprobs[0].to(device)
            ratios = torch.exp(logprobs - old_logprobs.detach())
                
            # Finding Surrogate Loss:
            state_values = self.policy.state_values[0].to(device)
            advantages = rewards - state_values.detach()
            surr1 = ratios * advantages
            surr2 = torch.clamp(ratios, 1-self.eps_clip, 1+self.eps_clip) * advantages
            loss = -torch.min(surr1, surr2) + 0.5*self.MseLoss(state_values, rewards) - 0.01*dist_entropy
            
            # take gradient step
            self.optimizer.zero_grad()
            loss.mean().backward()
            self.optimizer.step()
            
            self.policy.clearMemory()
        
        self.policy_old.clearMemory()
        
        # Copy new weights into old policy:
        self.policy_old.load_state_dict(self.policy.state_dict())
        
    def train(self):              
        running_reward = 0
        avg_length = 0
        episode_reward = 0
        save_reward = list()
        for epoch in range(self.num_episodes):
            state = self.env.reset()
#            self.init_game_setting()
            done = False
            t = 0
            while(not done):
                # Running policy_old:
                t += 1
                action = self.policy_old(state)
                state_n, reward, done, _ = self.env.step(action)
                
                # Saving state and reward:
                self.policy_old.states.append(state)
                self.policy_old.rewards.append(reward)
                
                state = state_n
                episode_reward += reward
                running_reward += reward
#                if render:
#                    env.render()
                if done:
                    break
            
            avg_length += t
            save_reward.append(episode_reward)
            episode_reward = 0
            # update after n episodes
            if epoch % self.n_update:
                self.update()
            
            # log
            if running_reward > (self.display_freq*200):
                print("########## Solved! ##########")
                torch.save(self.policy.state_dict(), 
                           './LunarLander_{}_{}_{}.pth'.format(
                            self.lr, self.betas[0], self.betas[1]))
                break
            
            if epoch % self.display_freq == 0:
                avg_length = int(avg_length/self.display_freq)
                running_reward = int((running_reward/self.display_freq))
                
                print('Episode {} \t avg length: {} \t reward: {}'.format(
                        epoch, avg_length, running_reward))
                running_reward = 0
                avg_length = 0
            np.save('PG_PPO_RewardCurve', save_reward)