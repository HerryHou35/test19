import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
import math

class LidarFilterNode(Node):
    def __init__(self):
        super().__init__('lidar_filter_node')
        
        # 1. 订阅小车原生的激光雷达话题（TurtleBot3 默认是 /scan）
        self.scan_sub = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            10
        )
        
        # 2. 声明发布者，把警告信号扔给你的大脑节点
        self.warning_pub = self.create_publisher(Bool, '/lidar_warning', 10)
        
        # 3. 设置防撞参数
        self.safe_distance = 0.3  # 只要前方 30 厘米内有东西就报警
        self.angle_range = 15     # 只盯着正前方左 15 度到右 15 度的扇形区域
        
        self.get_logger().info("🚀 Lidar Filter Node initialized and scanning...")

    def scan_callback(self, msg):
        # 雷达一圈通常有 360 个采样点（每度一个点）
        # msg.ranges 里面存的就是这 360 个点测出来的距离（米）
        num_points = len(msg.ranges)
        if num_points == 0:
            return

        is_obstacle_detected = False

        # 遍历雷达的所有采样点
        for i in range(num_points):
            # 计算当前点对应的角度（0度是正前方，顺时针/逆时针展开）
            angle = i * (360.0 / num_points)
            
            # 过滤出正前方范围：左边 (0 到 15度) 和 右边 (345 到 360度)
            if angle <= self.angle_range or angle >= (360.0 - self.angle_range):
                dist = msg.ranges[i]
                
                # 排除雷达死角或测不到的无效数据（0.0 或 inf）
                if isnan(dist) or isinf(dist) or dist <= 0.0:
                    continue
                
                # 💥 惊悚时刻：一旦发现正前方有人或墙挡着，且小于安全距离
                if dist < self.safe_distance:
                    is_obstacle_detected = True
                    # 抓到近处的障碍物了，直接跳出循环
                    break

        # 4. 包装成 Bool 消息轰出去
        warning_msg = Bool()
        warning_msg.data = is_obstacle_detected
        self.warning_pub.publish(warning_msg)
        
        if is_obstacle_detected:
            self.get_logger().warn("🚨 OBSTACLE DETECTED! Sending warning to brain...")

# 辅助函数：防止有些 ROS2 版本没导入 math 的判断
def isnan(x): return math.isnan(x)
def isinf(x): return math.isinf(x)

def main(args=None):
    rclpy.init(args=args)
    node = LidarFilterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
