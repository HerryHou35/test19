# Robot Programming — Unified ROS 2 Workspace

TurtleBot3 multi-modal control system: voice commands, hand-gesture teleop,
LiDAR-based obstacle avoidance, SLAM mapping, and a shared TTS Service.

## Where Services Are Used (PPT Reference)

```
┌──────────────────────────────────────────────────────────────┐
│                   /robot_speak SERVICE                       │
│               (robot_programming_interfaces/srv/Speak)       │
│                                                              │
│  Request:  string text   — "Obstacle detected!"              │
│  Response: bool success  — True                              │
│           string message — "Queued: Obstacle detected!"      │
│                                                              │
│  ┌─────────────┐                                            │
│  │ tts_server   │  <-- SERVICE SERVER                        │
│  │ (pyttsx3)    │      Listens on /robot_speak               │
│  └──────┬───────┘                                            │
│         │                                                    │
│   ┌─────┼─────────┬──────────────┐                           │
│   │     │         │              │                           │
│  ┌┴────┴┐   ┌────┴───┐    ┌─────┴──────┐                    │
│  │voice │   │lidar   │    │ arbiter    │   SERVICE CLIENTS   │
│  │control│  │filter  │    │  node      │                     │
│  │ node │   │ node   │    │            │                     │
│  └──────┘   └────────┘    └────────────┘                    │
│                                                              │
│  Why Service (not Topic)?                                    │
│  - Request-Reply pattern: caller knows TTS was queued        │
│  - Synchronous feedback: returns success/failure per request │
│  - One /robot_speak endpoint shared by ALL nodes             │
│  - If we used a Topic: no response, no confirmation,         │
│    multiple publishers on same topic = semantic ambiguity    │
└──────────────────────────────────────────────────────────────┘
```

## Package Structure

```
src/
├── robot_programming_interfaces/   # 纯 CMake 包 — 只管 .srv
│   ├── CMakeLists.txt              # rosidl_generate_interfaces
│   ├── package.xml                 # ament_cmake + member_of_group
│   └── srv/
│       └── Speak.srv               # /robot_speak 的 Service 类型定义
│
└── robot_programming/              # 纯 Python 包 — 零 CMake
    ├── package.xml                 # ament_python (build_type)
    ├── setup.py                    # data_files + entry_points (5 个节点)
    ├── setup.cfg
    ├── requirements.txt
    ├── launch/
    │   └── unified_launch.py       # 统一 launch 文件
    ├── robot_programming/
    │   ├── tts_server.py           # /robot_speak SERVICE SERVER
    │   ├── voice_control_node.py
    │   ├── lidar_filter_node.py
    │   ├── arbiter_node.py
    │   └── gesture_teleop_mediapipe.py
    ├── worlds/
    │   └── my_square_world.world
    ├── maps/
    │   ├── my_turtlebot_map.pgm
    │   └── my_turtlebot_map.yaml
    └── config/
```

## Full Communication Architecture

```
                    ┌──────────────────────┐
                    │     tts_server        │  SERVICE SERVER
                    │   /robot_speak        │
                    └──▲────────▲─────────▲─┘
                       │        │         │
              Service  │  Service│  Service│
              calls    │  calls  │  calls  │
                       │        │         │
Microphone → voice_control_node → /voice_tasks (JSON)
                                         ↓
LiDAR → /scan → lidar_filter_node → /lidar_warning (Bool)
                                         ↓
                                  arbiter_node → /cmd_vel → Gazebo

Webcam → gesture_teleop_mediapipe → /cmd_vel (direct teleop, optional)
```

| Node | Role | Communicates via |
|---|---|---|
| **tts_server** | **SERVICE SERVER** — wraps pyttsx3. Responds to `/robot_speak` requests. | **Service**: `/robot_speak` (Speak.srv) |
| voice_control_node | **SERVICE CLIENT** — calls `/robot_speak` for spoken feedback. Mic → Whisper STT → Ollama LLM → publishes JSON to `/voice_tasks`. Subscribes to `/lidar_warning`. | **Topic pub**: `/voice_tasks` (String/JSON) **Topic sub**: `/lidar_warning` (Bool) **Service client**: `/robot_speak` |
| lidar_filter_node | **SERVICE CLIENT** — calls `/robot_speak` on obstacle (throttled to 3 s). Reads `/scan`, checks forward 30 cone within 0.3 m. Publishes Bool. | **Topic sub**: `/scan` (LaserScan) **Topic pub**: `/lidar_warning` (Bool) **Service client**: `/robot_speak` |
| arbiter_node | **SERVICE CLIENT** — calls `/robot_speak` for "starting sequence" / "emergency stop" / "completed". Executes voice motion tasks on `/cmd_vel`, stops on LiDAR warning. | **Topic sub**: `/voice_tasks`, `/lidar_warning` **Topic pub**: `/cmd_vel` (Twist) **Service client**: `/robot_speak` |
| gesture_teleop_mediapipe | Direct teleop via webcam hand gestures. Publishes to `/cmd_vel`. | **Topic pub**: `/cmd_vel` (Twist) |

## Topic vs Service — When to Use Which

| | Topic | Service |
|---|---|---|
| **Pattern** | Publish-Subscribe (one-to-many) | Request-Reply (one-to-one) |
| **Use in this project** | `/scan`, `/cmd_vel`, `/voice_tasks`, `/lidar_warning` | `/robot_speak` |
| **Why?** | Continuous data streams; multiple subscribers may need the same data | A node needs to **request** TTS and get **confirmation** it was queued |
| **Analogy** | Radio broadcast (anyone can tune in) | Phone call (dial, get answer, hang up) |

## Prerequisites

- Ubuntu 24.04
- ROS 2 Jazzy Jalisco
- Gazebo Harmonic
- TurtleBot3 simulation packages

```bash
# Install TurtleBot3 simulation
sudo apt install ros-jazzy-turtlebot3-description ros-jazzy-turtlebot3-gazebo

# Install SLAM Toolbox
sudo apt install ros-jazzy-slam-toolbox

# Install Python dependencies
pip install -r src/robot_programming/requirements.txt
```

## Build

```bash
# From the workspace root
colcon build --symlink-install

# Source the workspace
source install/setup.bash
```

## Run

### Full simulation with voice control + LiDAR safety

```bash
ros2 launch robot_programming unified_launch.py
```

### Launch with specific components only

```bash
# Simulation only, no custom nodes
ros2 launch robot_programming unified_launch.py use_voice:=false use_arbiter:=false use_lidar_filter:=false use_tts:=false

# Without SLAM
ros2 launch robot_programming unified_launch.py use_slam:=false

# Gesture teleop instead of voice (requires webcam)
ros2 launch robot_programming unified_launch.py use_voice:=false use_arbiter:=false use_gesture:=true
```

### Run individual nodes (after simulation is running)

```bash
ros2 run robot_programming tts_server
ros2 run robot_programming voice_control_node
ros2 run robot_programming lidar_filter_node
ros2 run robot_programming arbiter_node
ros2 run robot_programming gesture_teleop_mediapipe
```

### Test the TTS service manually

```bash
ros2 service call /robot_speak robot_programming_interfaces/srv/Speak "{text: 'Hello from the command line'}"
```

## Topics & Services Reference

### Topics

| Topic | Type | Direction | Description |
|---|---|---|---|
| `/scan` | sensor_msgs/LaserScan | Gazebo → system | LiDAR scan data |
| `/lidar_warning` | std_msgs/Bool | filter → arbiter, voice | Obstacle within 0.3 m |
| `/voice_tasks` | std_msgs/String | voice → arbiter | JSON motion sequence |
| `/cmd_vel` | geometry_msgs/Twist | arbiter → robot | Motor velocity commands |

### Services

| Service | Type | Server | Clients |
|---|---|---|---|
| `/robot_speak` | robot_programming_interfaces/srv/Speak | tts_server | voice_control_node, lidar_filter_node, arbiter_node |

**Speak.srv definition:**

```
string text       # The sentence to speak via TTS
---
bool success      # True if speech was queued
string message    # Status / error description
```
