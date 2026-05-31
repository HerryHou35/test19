# 使用说明 — 启动后怎么控制机器人

## 你 Launch 之后发生了什么

```
unified_launch.py 一键启动了：
  ✅ Gazebo 仿真环境 + 自定义世界
  ✅ TurtleBot3 Burger 机器人
  ✅ RViz2 可视化
  ✅ SLAM Toolbox 建图
  ✅ tts_server          — TTS 语音播报服务
  ✅ lidar_filter_node   — 激光雷达障碍物检测
  ✅ arbiter_node        — 指令仲裁器 (→ /cmd_vel)
  ✅ voice_control_node  — 语音控制 (需要你说话)
```

**你按键盘没反应是正常的**——这个系统不是键盘控制的，是**语音**控制的。

---

## 三种控制方式

### 方式 1：语音控制（默认，推荐）

Voice Control Node 通过麦克风接收你的语音指令，转文字后发给 LLM 生成运动序列，然后由 Arbiter 执行。

**一句命令即可：**

```bash
ros2 launch robot_programming unified_launch.py
```

Launch 文件会**自动弹出一个新终端窗口**运行 voice_control_node，那个窗口里有交互式 `input()`，可以直接操作。

**在新弹出的终端窗口中操作：**

```
========================================
  TurtleBot3 Radar-Based Voice Control
========================================
Loading Whisper model...
System Ready

[Press Enter to Speak | Type 'test_lidar' for radar test]:
```

| 操作 | 效果 |
|---|---|
| 按 **Enter** | 开始录音 10 秒，说一句英文指令（如 "move forward 1 meter"） |
| 输入 **test_lidar** 回车 | 模拟激光雷达检测到障碍物，播报语音警告 |

**语音指令示例：**

| 你说 | 机器人行为 |
|---|---|
| "move forward 1 meter" | 前进 1 米 |
| "move backward 0.5 meters" | 后退 0.5 米 |
| "turn left 90 degrees" | 左转 90 度 |
| "turn right 45 degrees" | 右转 45 度 |
| "stop" | 立即停止 |

---

### 方式 2：键盘控制（最直观）

安装 teleop 工具，用键盘 WASD 直接遥控：

```bash
# 安装
sudo apt install ros-jazzy-teleop-twist-keyboard

# 启动仿真（不要 arbiter，让键盘直接控制 cmd_vel）
ros2 launch robot_programming unified_launch.py use_voice:=false use_arbiter:=false

# 新终端，键盘控制
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

**按键说明：**

```
前进:  i (或 W)
后退:  , (或 S)
左转:  j (或 A)
右转:  l (或 D)
停止:  k (或空格)

q/z : 加/减速
按 Ctrl+C 退出
```

---

### 方式 3：手势控制（需要摄像头）

```bash
ros2 launch robot_programming unified_launch.py use_voice:=false use_arbiter:=false use_gesture:=true
```

会自动弹出一个新窗口显示摄像头画面。对着摄像头做手势即可控制机器人。

**手势对照表：**

| 手势 | 行为 |
|---|---|
| 握拳 | 停止 |
| 只伸食指 | 前进 |
| 只伸拇指 | 左转 |
| 只伸小指 | 右转 |
| 拇指 + 食指 + 中指（三指） | 后退 |
| 五指张开（4 指以上） | 前进 |

> **注意：** 摄像头窗口必须保持在前台焦点才能捕获手势。`use_arbiter:=false` 很重要，否则 arbiter 和 gesture 同时往 `/cmd_vel` 发指令会冲突。

---

## 验证一切正常

```bash
# 1. 查看所有运行中的节点
ros2 node list

# 2. 查看激光雷达数据（确认 /scan 有数据）
ros2 topic echo /scan --once

# 3. 查看激光雷达警告状态
ros2 topic echo /lidar_warning

# 4. 测试 TTS 语音服务
ros2 service call /robot_speak robot_programming_interfaces/srv/Speak "{text: 'Hello world'}"

# 5. 手动发一条语音指令到 Arbiter
ros2 topic pub /voice_tasks std_msgs/String 'data: "{\"tasks\":[{\"type\":\"move_forward\",\"distance\":0.5}]}"'

# 6. 查看 cmd_vel 是否有数据
ros2 topic echo /cmd_vel
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 按 i/j/l 没反应 | 系统默认是语音模式，不是键盘模式 | 用方式 2 装 teleop_twist_keyboard |
| 机器人不动 | arbiter 没收到 /voice_tasks | 终端里按 Enter 说话，或者手动 pub 一条指令测试 |
| 说话后机器人还是不动 | Ollama API 可能调用失败 | 看终端里的报错信息，检查 API key 和网络 |
| 激光雷达报警不停 | 障碍物靠太近 | 确认 /scan topic 有数据，调整 safe_distance 参数 |
| TTS 不发声 | tts_server 没启动或 pyttsx3 缺包 | `pip install pyttsx3`，检查 `ros2 service list` 是否包含 `/robot_speak` |

---

## 推荐的日常开发流程

```bash
# 一句命令启动全部 (语音窗口会自动弹出)
ros2 launch robot_programming unified_launch.py

# 想要键盘遥控时，关掉自动弹出的语音窗口，然后：
# Ctrl+C 停掉当前 launch
ros2 launch robot_programming unified_launch.py use_voice:=false use_arbiter:=false
# 新终端
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```
