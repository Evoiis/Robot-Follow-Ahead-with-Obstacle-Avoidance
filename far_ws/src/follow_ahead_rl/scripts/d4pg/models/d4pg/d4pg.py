import time
import numpy as np
import copy
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import os

from utils.utils import OUNoise
from utils.reward_plot import plot_rewards
from utils.logger import Logger

from .networks import PolicyNetwork, ValueNetwork

def _l2_project(z_p, p, z_q):
    """Projects distribution (z_p, p) onto support z_q under L2-metric over CDFs.
    The supports z_p and z_q are specified as tensors of distinct atoms (given
    in ascending order).
    Let Kq be len(z_q) and Kp be len(z_p). This projection works for any
    support z_q, in particular Kq need not be equal to Kp.
    Args:
      z_p: Tensor holding support of distribution p, shape `[batch_size, Kp]`.
      p: Tensor holding probability values p(z_p[i]), shape `[batch_size, Kp]`.
      z_q: Tensor holding support to project onto, shape `[Kq]`.
    Returns:
      Projection of (z_p, p) onto support z_q under Cramer distance.
    """
    # Broadcasting of tensors is used extensively in the code below. To avoid
    # accidental broadcasting along unintended dimensions, tensors are defensively
    # reshaped to have equal number of dimensions (3) throughout and intended # shapes are indicated alongside tensor definitions. To reduce verbosity,
    # extra dimensions of size 1 are inserted by indexing with `None` instead of
    # `tf.expand_dims()` (e.g., `x[:, None, :]` reshapes a tensor of shape
    # `[k, l]' to one of shape `[k, 1, l]`).

    ## l2_projection ##
    # Adapted for PyTorch from: https://github.com/deepmind/trfl/blob/master/trfl/dist_value_ops.py
    # Projects the target distribution onto the support of the original network [Vmin, Vmax]

    z_p = torch.tensor(z_p).float()

    # Extract vmin and vmax and construct helper tensors from z_q
    vmin, vmax = z_q[0], z_q[-1]

    d_pos = torch.cat([z_q, vmin[None]], 0)[1:]
    d_neg = torch.cat([vmax[None], z_q], 0)[:-1]

    # Clip z_p to be in new support range (vmin, vmax)
    z_p = torch.clamp(z_p, vmin, vmax)[:, None, :]

    # Get the distance between atom values in support
    d_pos = (d_pos - z_q)[None, :, None]
    d_neg = (z_q - d_neg)[None, :, None]
    z_q = z_q[None, :, None]

    d_neg = torch.where(d_neg>0, 1./d_neg, torch.zeros(d_neg.shape))
    d_pos = torch.where(d_pos>0, 1./d_pos, torch.zeros(d_pos.shape))

    delta_qp = z_p - z_q
    d_sign = (delta_qp >= 0).type(p.dtype)

    delta_hat = (d_sign * delta_qp * d_pos) - ((1. - d_sign) * delta_qp * d_neg)
    p = p[:, None, :]
    return torch.sum(torch.clamp(1. - delta_hat, 0., 1.) * p, -1)


class LearnerD4PG(object):
    """Policy and value network update routine. """

    def __init__(self, config, policy_net, target_policy_net, learner_w_queue, log_dir=''):
        hidden_dim = config['dense_size']
        state_dim = config['state_dims']
        action_dim = config['action_dims']
        value_lr = config['critic_learning_rate']
        policy_lr = config['actor_learning_rate']
        self.best_policy_loss = 10000
        self.best_value_loss = 10000
        v_min = config['v_min']
        v_max = config['v_max']
        self.path_weight_value = config['value_weights']
        self.path_weight_policy = config['policy_weights']
        self.run_name = config['run_name']
        num_atoms = config['num_atoms']
        self.counter = 0
        self.device = config['device']
        self.max_steps = config['max_ep_length']
        self.num_train_steps = config['num_steps_train']
        self.batch_size = config['batch_size']
        self.tau = config['tau']
        self.gamma = config['discount_rate']
        self.log_dir = log_dir
        self.prioritized_replay = config['replay_memory_prioritized']
        self.learner_w_queue = learner_w_queue

        self.logger = Logger(f"{log_dir}/learner", name="{}/learner".format(self.run_name), project_name=config["project_name"])
        self.path_weight_run = self.logger.get_log_dir()
        if not os.path.exists(self.path_weight_run):
            os.makedirs(self.path_weight_run)

        # Noise process
        self.ou_noise = OUNoise(dim=config["action_dim"], low=config["action_low"], high=config["action_high"])

        # Value and policy nets
        self.value_net = ValueNetwork(state_dim, action_dim, hidden_dim, v_min, v_max, num_atoms, device=self.device)
        self.target_value_net = ValueNetwork(state_dim, action_dim, hidden_dim, v_min, v_max, num_atoms, device=self.device)
        if os.path.exists(config['value_weights_best']):
            self.value_net.load_state_dict(torch.load(config['value_weights_best']))
            self.target_value_net = copy.deepcopy(self.value_net)
        else:
            print("cannot load value_net: {}".format(config['value_weights_best']))

        self.policy_net = policy_net #PolicyNetwork(state_dim, action_dim, hidden_dim, device=self.device)
        self.target_policy_net = target_policy_net

        for target_param, param in zip(self.target_value_net.parameters(), self.value_net.parameters()):
            target_param.data.copy_(param.data)

        for target_param, param in zip(self.target_policy_net.parameters(), self.policy_net.parameters()):
            target_param.data.copy_(param.data)

        self.value_optimizer = optim.Adam(self.value_net.parameters(), lr=value_lr)
        self.policy_optimizer = optim.Adam(self.policy_net.parameters(), lr=policy_lr)

        self.value_criterion = nn.BCELoss(reduction='none')

    def ddpg_update(self, batch, replay_priority_queue, update_step, min_value=-np.inf, max_value=np.inf):
        update_time = time.time()

        state, action, reward, next_state, done, gamma, weights, inds = batch

        state = np.asarray(state)
        action = np.asarray(action)
        reward = np.asarray(reward)
        next_state = np.asarray(next_state)
        done = np.asarray(done)
        weights = np.asarray(weights)
        inds = np.asarray(inds).flatten()

        state = torch.from_numpy(state).float().to(self.device)
        next_state = torch.from_numpy(next_state).float().to(self.device)
        action = torch.from_numpy(action).float().to(self.device)
        reward = torch.from_numpy(reward).float().unsqueeze(1).to(self.device)
        done = torch.from_numpy(done).float().unsqueeze(1).to(self.device)

        # ------- Update critic -------

        # Predict next actions with target policy network
        next_action = self.target_policy_net(next_state)

        # Predict Z distribution with target value network
        target_value = self.target_value_net.get_probs(next_state, next_action.detach())
        target_z_atoms = self.value_net.z_atoms

        # Batch of z-atoms
        target_Z_atoms = np.repeat(np.expand_dims(target_z_atoms, axis=0), self.batch_size,
                                   axis=0)  # [batch_size x n_atoms]
        # Value of terminal states is 0 by definition

        target_Z_atoms *= (done.cpu().int().numpy() == 0)

        # Apply bellman update to each atom (expected value)
        reward = reward.cpu().float().numpy()
        target_Z_atoms = reward + (target_Z_atoms * self.gamma)
        target_z_projected = _l2_project(torch.from_numpy(target_Z_atoms).cpu().float(),
                                         target_value.cpu().float(),
                                         torch.from_numpy(self.value_net.z_atoms).cpu().float())

        critic_value = self.value_net.get_probs(state, action)#self.value_net(state, action)

        critic_value = critic_value.to(self.device)

        value_loss = self.value_criterion(critic_value,
                                     torch.autograd.Variable(target_z_projected, requires_grad=False).cuda())

        value_loss = value_loss.mean(axis=1)

        # Update priorities in buffer
        td_error = value_loss.cpu().detach().numpy().flatten()

        priority_epsilon = 1e-4
        if self.prioritized_replay:
            weights_update = np.abs(td_error) + priority_epsilon
            replay_priority_queue.put((inds, weights_update))
            value_loss = value_loss * torch.tensor(weights).cuda().float()

        value_loss = value_loss.mean()

        self.value_optimizer.zero_grad()
        value_loss.backward()
        self.value_optimizer.step()

        # -------- Update actor -----------

        policy_loss = self.value_net.get_probs(state, self.policy_net(state))
        policy_loss = policy_loss * torch.tensor(self.value_net.z_atoms).float().cuda()
        policy_loss = torch.sum(policy_loss, dim=1)
        policy_loss = -policy_loss.mean()

        self.policy_optimizer.zero_grad()
        policy_loss.backward()
        self.policy_optimizer.step()

        for target_param, param in zip(self.target_value_net.parameters(), self.value_net.parameters()):
            target_param.data.copy_(
                target_param.data * (1.0 - self.tau) + param.data * self.tau
            )

        for target_param, param in zip(self.target_policy_net.parameters(), self.policy_net.parameters()):
            target_param.data.copy_(
                target_param.data * (1.0 - self.tau) + param.data * self.tau
            )

        # Send updated learner to the queue
        if not self.learner_w_queue.full():
            params = [p.data.cpu().detach().numpy() for p in self.policy_net.parameters()]
            self.learner_w_queue.put(params)

        # Logging
        step = update_step.value
        self.logger.scalar_summary("learner/policy_loss", policy_loss.item(), step)
        self.logger.scalar_summary("learner/value_loss", value_loss.item(), step)
        self.logger.scalar_summary("learner/learner_update_timing", time.time() - update_time, step)
        self.counter += 1
        if self.counter < 100:
           return
        if self.best_policy_loss > policy_loss.item():
            print("saving best policy loss")
            self.best_policy_loss = policy_loss.item()
            torch.save(self.policy_net.state_dict(), os.path.join(self.path_weight_run,  "policy_best.pt"))
            torch.save(self.policy_net.state_dict(), self.path_weight_policy + "policy_best2.pt")
            self.logger.save_model("policy_best.pt")
        if self.best_value_loss > value_loss.item():
            print("saving best value loss")
            self.best_value_loss= value_loss.item()
            torch.save(self.value_net.state_dict(), self.path_weight_value + "value_best2.pt")
            torch.save(self.value_net.state_dict(), os.path.join(self.path_weight_run,  "value_best.pt"))
            self.logger.save_model("value_best.pt")
        if self.counter % 10000 == 0:
            print("saving weights")
            torch.save(self.policy_net.state_dict(), os.path.join(self.path_weight_run,  "{}_policy.pt".format(self.counter)))
            torch.save(self.value_net.state_dict(), os.path.join(self.path_weight_run, "{}_value.pt".format(self.counter)))
            self.logger.save_model("{}_policy.pt".format(self.counter))
            self.logger.save_model("{}_value.pt".format(self.counter))

    def run(self, training_on, batch_queue, replay_priority_queue, update_step):
        while update_step.value < self.num_train_steps:
            if batch_queue.empty():
                continue

            batch = batch_queue.get()
            self.ddpg_update(batch, replay_priority_queue, update_step)
            update_step.value += 1

            if update_step.value % 100 == 0:
                print("Training step ", update_step.value)

        training_on.value = 0
        plot_rewards(self.log_dir)
        print("Exit learner.")
