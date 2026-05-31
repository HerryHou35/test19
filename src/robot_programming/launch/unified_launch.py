"""
Unified launch file for the TurtleBot3 Robot Programming project.

Launches:
  - Gazebo Harmonic simulation with the custom square world
  - TurtleBot3 Burger robot (spawn + state publisher)
  - ros_gz_bridge (cmd_vel, scan, odom, tf, clock)
  - Static TF publishers (base_scan, base_footprint, base_link)
  - RViz2 (optional)
  - SLAM Toolbox (optional)

Services:
  - tts_server            — /robot_speak service (pyttsx3 TTS)

Custom nodes:
  - lidar_filter_node    — LiDAR obstacle detection → /lidar_warning
  - voice_control_node    — Speech → LLM → /voice_tasks
  - arbiter_node          — /voice_tasks + /lidar_warning → /cmd_vel
  - gesture_teleop_mediapipe (off by default — requires webcam + display)

Usage:
  ros2 launch robot_programming unified_launch.py

  ros2 launch robot_programming unified_launch.py use_rviz:=false
  ros2 launch robot_programming unified_launch.py use_slam:=false
  ros2 launch robot_programming unified_launch.py use_voice:=false
  ros2 launch robot_programming unified_launch.py use_gesture:=true
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
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # ------------------------------------------------------------------
    # Package paths
    # ------------------------------------------------------------------
    pkg_robot_programming = get_package_share_directory('robot_programming')
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
        'use_slam', default_value='true',
        description='Launch SLAM Toolbox'
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz', default_value='true',
        description='Launch RViz2'
    )
    use_voice_arg = DeclareLaunchArgument(
        'use_voice', default_value='true',
        description='Launch Voice Control Node'
    )
    use_arbiter_arg = DeclareLaunchArgument(
        'use_arbiter', default_value='true',
        description='Launch Arbiter Node'
    )
    use_gesture_arg = DeclareLaunchArgument(
        'use_gesture', default_value='false',
        description='Launch Gesture Teleop Node (requires webcam + display)'
    )
    use_tts_arg = DeclareLaunchArgument(
        'use_tts', default_value='true',
        description='Launch TTS Service Server (/robot_speak)'
    )
    use_lidar_filter_arg = DeclareLaunchArgument(
        'use_lidar_filter', default_value='true',
        description='Launch LiDAR Filter Node'
    )

    # ------------------------------------------------------------------
    # 1. Gazebo Harmonic simulation
    # ------------------------------------------------------------------
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': f'-r {world_file_path}'}.items(),
    )

    # ------------------------------------------------------------------
    # 2. Robot State Publisher (URDF)
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
    # 3. Spawn TurtleBot3 in Gazebo
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
    # 6. Static TF publishers (frame aliases for SLAM / Nav2)
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
    # 8. TTS Service Server — /robot_speak (called by all other nodes)
    # ------------------------------------------------------------------
    tts_server = Node(
        package='robot_programming',
        executable='tts_server',
        name='tts_server',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_tts')),
    )

    # ------------------------------------------------------------------
    # 9. LiDAR Filter Node — obstacle detection → /lidar_warning
    # ------------------------------------------------------------------
    lidar_filter_node = Node(
        package='robot_programming',
        executable='lidar_filter_node',
        name='lidar_filter_node',
        output='screen',
        parameters=[{'use_sim_time': True}],
        condition=IfCondition(LaunchConfiguration('use_lidar_filter')),
    )

    # ------------------------------------------------------------------
    # 10. Voice Control Node — mic → STT → LLM → /voice_tasks
    #     Launched in a new gnome-terminal because it needs interactive
    #     stdin (input() for "Press Enter to Speak").
    # ------------------------------------------------------------------
    voice_control_node = ExecuteProcess(
        cmd=[
            'gnome-terminal', '--', 'bash', '-c',
            'source /opt/ros/jazzy/setup.bash && '
            'source install/setup.bash && '
            'ros2 run robot_programming voice_control_node; '
            'exec bash'
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_voice')),
    )

    # ------------------------------------------------------------------
    # 11. Arbiter Node — /voice_tasks + /lidar_warning → /cmd_vel
    # ------------------------------------------------------------------
    arbiter_node = Node(
        package='robot_programming',
        executable='arbiter_node',
        name='arbiter_node',
        output='screen',
        parameters=[{'use_sim_time': True}],
        condition=IfCondition(LaunchConfiguration('use_arbiter')),
    )

    # ------------------------------------------------------------------
    # 12. Gesture Teleop Node — webcam → hand gestures → /cmd_vel
    #     OFF by default. Enable with: use_gesture:=true
    #     NOTE: Requires a webcam.  Launched in its own terminal for the
    #           OpenCV camera window to render correctly.
    #     Tip: disable arbiter too — use_arbiter:=false
    # ------------------------------------------------------------------
    gesture_node = ExecuteProcess(
        cmd=[
            'gnome-terminal', '--', 'bash', '-c',
            'source /opt/ros/jazzy/setup.bash && '
            'source install/setup.bash && '
            'ros2 run robot_programming gesture_teleop_mediapipe; '
            'exec bash'
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_gesture')),
    )

    # ------------------------------------------------------------------
    # Return
    # ------------------------------------------------------------------
    return LaunchDescription([
        # Environment — force localhost for multi-cast restricted networks
        SetEnvironmentVariable(name='ROS_LOCALHOST_ONLY', value='1'),
        SetEnvironmentVariable(name='GZ_IP', value='127.0.0.1'),

        # Launch arguments
        use_slam_arg,
        use_rviz_arg,
        use_voice_arg,
        use_arbiter_arg,
        use_tts_arg,
        use_gesture_arg,
        use_lidar_filter_arg,

        # Simulation & robot
        gz_sim,
        robot_state_publisher,
        gz_spawn_robot,
        rviz2_node,
        gz_bridge,

        # TF hacks
        lidar_static_tf,
        base_footprint_tf,
        base_link_tf,

        # SLAM
        slam_toolbox,

        # Custom nodes
        tts_server,
        lidar_filter_node,
        voice_control_node,
        arbiter_node,
        gesture_node,
    ])
