# Robot Follow Ahead with Obstacle Avoidance

> Comparing Model-Based Methods to Predict Human Trajectory in Follow-Ahead Problem

By Emma Hughson, Kai Ho Anthony Cheung, and Khizr Ali Pardhan. An expansion upon [*LBGP: Learning Based Goal Planning for Autonomous Following in Front*](https://arxiv.org/pdf/2011.03125v1.pdf). 

## Meta 
Branch: *Purpose*  
* Main: {Team} This branch contains the working environment designated for testing the HINN and trajectory planner solution.  For evaluation us the hinn_dh_eval.
* World Models: {Emma & K. Ali} This branch contains the working environment designated for testing World Model implementation.
* Development: {K. Ali} Everything important in merged into **Main** 
* Monte Carlo: {Emma} Everything important in merged into **World Models**
* Other Branches: {Anthony} Are for the ROS environment. All work is merged into **Main**


To run, you will need to, in sourced terminals & in-order, run the following [launch file](far_ws/src/follow_ahead_rl/launch), `turtlebot.launch`, and code like [move_test.py](far_ws/src/follow_ahead_rl/scripts/move_test.py) or [td_ddpg_continuous.py](far_ws/src/follow_ahead_rl/scripts/td_ddpg_continuous.py)


## Introduction

**What is Follow-Ahead?** Following-ahead algorithms use machine learning to predict human trajectory to stay ahead of humans. Follow-behind algorithms have had more recognition. For example, one application is a follow-behind shopping cart. **But,** there is a lack of security. 

**Why Model-Based Methods: **The field of reinforcement learning is **primarily focused** on model-free methods. Model-based methods have been shown to be more efficient than model-free.

**What our solution is: Extending the work** of Nikdel et al., we will be using model-based algorithms with the addition of obstacle avoidance.

![img](https://lh6.googleusercontent.com/vcm2ETgHOHVG5tV7dPMG_KrdsmWEvy1fmwErLSB3Xl8i5PEUYqGL5HrypWWaBUQ7Hr0-hlVixG0MCVV4tjZJWhsgl1mtOYrb8qH3Eo95ZqfhsGuMQ_8KH-owDRc3l7JuLzrPFdGCpWI)

## Methods

Our approach is to use a popular model-based learning algorithm (i.e., World Model) along with executing our own Human Intent Neural Network (HINN).

**World Model**: 

> Long Short Term Memory Network -> Controller

**HINN + Heuristic Search:** The Human Intent Neural Network is a feed forward neural network, which outputs the prediction of the next human state. Prediction is used to generate a goal for the robot. Heuristic search algorithms: Monte Carlo Tree Search (MCTS) or Distance Heuristic.

We have extended the given Gym environment to include obstacles, obstacle avoidance, and support for our pipeline. We have also started training the HINN, as well as implementing the heuristics and world-model algorithm.

### ROS & Gazebo 

We used Gazebo to simulate the robot follow-ahead scenario. Using the ROS navigation stack with TEB Local Planner we implemented obstacle avoidance. With a combination of ROS, Gazebo, and Gym we generated training data and control the simulation.

![img](https://lh6.googleusercontent.com/JbH-ANjURLGVGEhtxxVbhi0PGxWdmi6QsuQxo64STBQ5n4hA3QDlsZUstYbZj7VStTNPTRWmdh8nTL38WECI5HPZLJ-C5t0Avw3Jqa1YRa027D-7W-ioJ6wt6H6gZJ5kAd4Gzr61JCw)

## Conclusion 

We have seen promising preliminary results from the HINN. Currently, we cannot state if model-based is better than model-free. In the next week, the model-based algorithms will be completed using obstacle avoidance. If time allows, we hope to utilize MCTS to choose the best robot action. Changing our obstacle avoidance to use a **costmap** to facilitate a transition to the real world.
