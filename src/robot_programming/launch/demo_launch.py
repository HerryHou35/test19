"""
Demo launch file — one command opens 3 terminals for 3 control modes.

  Terminal 1 (main) : Gazebo + robot + LiDAR + TTS + GESTURE (camera window)
  Terminal 2         : VOICE CONTROL (voice_control_node + arbiter)
  Terminal 3         : KEYBOARD CONTROL (teleop_twist_keyboard)

Only use ONE control mode at a time. The others sit idle.

Usage:
  ros2 launch robot_programming demo_launch.py

  # Skip SLAM or RViz if you want faster startup:
  ros2 launch robot_programming demo_launch.py use_slam:=false use_rviz:=false
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():

    pkg_robot_programming = get_package_share_directory('robot_programming')

    # Compute absolute path to install/setup.bash.
    # pkg_share = {ws}/install/robot_programming/share/robot_programming
    # Go up 3 levels to reach {ws}/install
    install_prefix = os.path.dirname(
        os.path.dirname(
            os.path.dirname(pkg_robot_programming)
        )
    )
    install_setup = os.path.join(install_prefix, 'setup.bash')

    SETUP_CMD = (
        f'source /opt/ros/jazzy/setup.bash && '
        f'source {install_setup} && '
        'export TURTLEBOT3_MODEL=burger'
    )
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    pkg_turtlebot3_desc = get_package_share_directory('turtlebot3_description')
    pkg_turtlebot3_gazebo = get_package_share_directory('turtlebot3_gazebo')
    pkg_slam_toolbox = get_package_share_directory('slam_toolbox')

    world_file_path = os.path.join(
        pkg_robot_programming, 'worlds', 'my_square_world.world'
    )
    rviz_config_path = os.path.join(
        pkg_turtlebot3_desc, 'rviz', 'model.rviz'
    )

    # ------------------------------------------------------------------
    # Launch arguments
    # ------------------------------------------------------------------
    use_slam_arg = DeclareLaunchArgument(
        'use_slam', default_value='true'
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz', default_value='true'
    )

    # ------------------------------------------------------------------
    # 1. Gazebo
    # ------------------------------------------------------------------
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': f'-r {world_file_path}'}.items(),
    )

    # ------------------------------------------------------------------
    # 2. Robot State Publisher
    # ------------------------------------------------------------------
    urdf_file = os.path.join(
        pkg_turtlebot3_desc, 'urdf', 'turtlebot3_burger.urdf'
    )
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_desc,
        }],
    )

    # ------------------------------------------------------------------
    # 3. Spawn robot
    # ------------------------------------------------------------------
    model_sdf_path = os.path.join(
        pkg_turtlebot3_gazebo, 'models', 'turtlebot3_burger', 'model.sdf'
    )
    gz_spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-world', 'my_square_world',
            '-file', model_sdf_path,
            '-name', 'turtlebot3_burger',
            '-x', '0.3', '-y', '0.3', '-z', '0.05',
        ],
        parameters=[{'use_sim_time': True}],
    )

    # ------------------------------------------------------------------
    # 4. RViz2
    # ------------------------------------------------------------------
    rviz2_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        parameters=[{'use_sim_time': True}],
        arguments=['-d', rviz_config_path],
        condition=IfCondition(LaunchConfiguration('use_rviz')),
    )

    # ------------------------------------------------------------------
    # 5. ros_gz_bridge
    # ------------------------------------------------------------------
    gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        output='screen',
        arguments=[
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/model/turtlebot3_burger/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            '/model/turtlebot3_burger/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V',
        ],
        remappings=[
            ('/scan', '/scan'),
            ('/model/turtlebot3_burger/odometry', '/odom'),
            ('/model/turtlebot3_burger/tf', '/tf'),
        ],
    )

    # ------------------------------------------------------------------
    # 6. Static TF publishers
    # ------------------------------------------------------------------
    lidar_static_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='lidar_static_tf',
        arguments=[
            '0', '0', '0', '0', '0', '0',
            'turtlebot3_burger/base_scan', 'base_scan',
        ],
        output='screen',
    )
    base_footprint_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_footprint_tf',
        arguments=[
            '0', '0', '0', '0', '0', '0',
            'turtlebot3_burger/base_footprint', 'base_footprint',
        ],
        output='screen',
    )
    base_link_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_tf',
        arguments=[
            '0', '0', '0', '0', '0', '0',
            'turtlebot3_burger/base_link', 'base_link',
        ],
        output='screen',
    )

    # ------------------------------------------------------------------
    # 7. SLAM Toolbox
    # ------------------------------------------------------------------
    slam_toolbox = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            os.path.join(
                pkg_slam_toolbox, 'config', 'mapper_params_online_async.yaml'
            ),
            {
                'use_sim_time': True,
                'transform_timeout': 3.0,
                'odom_frame': 'odom',
                'base_frame': 'base_footprint',
            },
        ],
        condition=IfCondition(LaunchConfiguration('use_slam')),
    )

    # ------------------------------------------------------------------
    # 8. TTS Service Server
    # ------------------------------------------------------------------
    tts_server = Node(
        package='robot_programming',
        executable='tts_server',
        name='tts_server',
        output='screen',
    )

    # ------------------------------------------------------------------
    # 9. LiDAR Filter Node
    # ------------------------------------------------------------------
    lidar_filter_node = Node(
        package='robot_programming',
        executable='lidar_filter_node',
        name='lidar_filter_node',
        output='screen',
        parameters=[{'use_sim_time': True}],
    )

    # ==================================================================
    # Three control-mode terminals (use ONE at a time)
    # ==================================================================

    # ---- Terminal 2: VOICE CONTROL ----
    voice_terminal = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            '--title', 'VOICE CONTROL - Press Enter to speak',
            '--', 'bash', '-c',
            f'{SETUP_CMD} && '
            'echo "========== VOICE CONTROL ==========" && '
            'echo "Arbiter running in background (logs hidden)." && '
            'echo "Press Enter to speak a command." && '
            'echo "" && '
            'ros2 run robot_programming arbiter_node '
            '--ros-args --log-level ERROR '
            '2>/dev/null & '
            'ARBITER_PID=$!; '
            'sleep 0.5; '
            'ros2 run robot_programming voice_control_node; '
            'kill $ARBITER_PID 2>/dev/null; '
            'exec bash'
        ],
        output='screen',
    )

    # ---- GESTURE CONTROL (gnome-terminal for DISPLAY=:0) ----
    gesture_proc = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            '--title', 'GESTURE CONTROL - Show hand to camera',
            '--', 'bash', '-c',
            f'{SETUP_CMD} && '
            'echo "========== GESTURE CONTROL ==========" && '
            'echo "  Fist      -> Stop" && '
            'echo "  Open hand -> Forward" && '
            'echo "  Index     -> Forward" && '
            'echo "  Thumb     -> Left" && '
            'echo "  Pinky     -> Right" && '
            'echo "" && '
            'ros2 run robot_programming gesture_teleop_mediapipe; '
            'exec bash'
        ],
        output='screen',
    )

    # ---- Terminal 4: KEYBOARD CONTROL ----
    keyboard_terminal = ExecuteProcess(
        cmd=[
            'gnome-terminal',
            '--title', 'KEYBOARD CONTROL - i=forward ,=back j=left l=right',
            '--', 'bash', '-c',
            f'{SETUP_CMD} && '
            'echo "========== KEYBOARD CONTROL ==========" && '
            'echo "  i : forward      , : backward" && '
            'echo "  j : left         l : right" && '
            'echo "  k : stop" && '
            'echo "" && '
            'ros2 run teleop_twist_keyboard teleop_twist_keyboard; '
            'exec bash'
        ],
        output='screen',
    )

    # ------------------------------------------------------------------
    # Return
    # ------------------------------------------------------------------
    return LaunchDescription([
        SetEnvironmentVariable(name='ROS_LOCALHOST_ONLY', value='1'),
        SetEnvironmentVariable(name='GZ_IP', value='127.0.0.1'),

        use_slam_arg,
        use_rviz_arg,

        # Infrastructure
        gz_sim,
        robot_state_publisher,
        gz_spawn_robot,
        rviz2_node,
        gz_bridge,
        lidar_static_tf,
        base_footprint_tf,
        base_link_tf,
        slam_toolbox,
        tts_server,
        lidar_filter_node,

        # Three control terminals
        voice_terminal,
        gesture_proc,
        keyboard_terminal,
    ])
