"""
Launch file for REAL TurtleBot3 hardware (no Gazebo, no simulation).

Opens 3 terminals for 3 control modes.

Usage:
  ros2 launch robot_programming real_robot_launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    pkg_robot_programming = get_package_share_directory('robot_programming')
    install_prefix = os.path.dirname(
        os.path.dirname(os.path.dirname(pkg_robot_programming))
    )
    install_setup = os.path.join(install_prefix, 'setup.bash')

    SETUP_CMD = (
        f'source /opt/ros/jazzy/setup.bash && '
        f'source {install_setup} && '
        'export TURTLEBOT3_MODEL=burger'
    )

    use_tts_arg = DeclareLaunchArgument(
        'use_tts', default_value='true'
    )
    use_gesture_arg = DeclareLaunchArgument(
        'use_gesture', default_value='true'
    )

    # ------------------------------------------------------------------
    # TTS Service Server
    # ------------------------------------------------------------------
    tts_server = Node(
        package='robot_programming',
        executable='tts_server',
        name='tts_server',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_tts')),
    )

    # ------------------------------------------------------------------
    # Terminal 2: VOICE CONTROL (arbiter + voice node)
    # ------------------------------------------------------------------
    voice_terminal = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            '--title', 'VOICE CONTROL - Press Enter to speak',
            '--', 'bash', '-c',
            f'{SETUP_CMD} && '
            'echo "========== VOICE CONTROL ==========" && '
            'echo "Arbiter running in background." && '
            'echo "Press Enter to speak a command." && '
            'echo "" && '
            'ros2 run robot_programming arbiter_node & '
            'ARBITER_PID=$!; '
            'sleep 0.5; '
            'ros2 run robot_programming voice_control_node; '
            'kill $ARBITER_PID 2>/dev/null; '
            'exec bash'
        ],
        output='screen',
    )

    # ------------------------------------------------------------------
    # Terminal 3: GESTURE CONTROL
    # ------------------------------------------------------------------
    gesture_terminal = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            '--title', 'GESTURE CONTROL - Show hand to camera',
            '--', 'bash', '-c',
            f'{SETUP_CMD} && '
            'echo "========== GESTURE CONTROL ==========" && '
            'echo "  Fist      -> Stop" && '
            'echo "  Open hand -> Forward" && '
            'echo "  Thumb     -> Left" && '
            'echo "  Pinky     -> Right" && '
            'echo "" && '
            'ros2 run robot_programming gesture_teleop_mediapipe; '
            'exec bash'
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_gesture')),
    )

    return LaunchDescription([
        use_tts_arg,
        use_gesture_arg,
        tts_server,
        voice_terminal,
        gesture_terminal,
    ])
