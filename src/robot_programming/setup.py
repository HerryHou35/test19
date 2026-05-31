import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'robot_programming'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name,
            ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.py')),
        (os.path.join('share', package_name, 'worlds'),
            glob('worlds/*')),
        (os.path.join('share', package_name, 'maps'),
            glob('maps/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Team',
    maintainer_email='team@example.com',
    description='Unified ROS 2 package: voice control, LiDAR safety, gesture teleop, TTS service, and motion arbiter.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'tts_server = robot_programming.tts_server:main',
            'voice_control_node = robot_programming.voice_control_node:main',
            'lidar_filter_node = robot_programming.lidar_filter_node:main',
            'gesture_teleop_mediapipe = robot_programming.gesture_teleop_mediapipe:main',
            'arbiter_node = robot_programming.arbiter_node:main',
        ],
    },
)
