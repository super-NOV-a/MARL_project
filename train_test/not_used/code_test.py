import os

# 设置文件夹路径
folder_path = r"E:\PyProjects\MARL_project\train_test\test_4\agent_paths\c3v1mahpo_9200"

# 初始化计数器
success_true_count = 0  # 统计 "成功" 位置 True 的次数
success_false_count = 0  # 统计 "成功" 位置 False 的次数
confront_true_count = 0  # 统计 "对抗" 位置 True 的次数
confront_false_count = 0  # 统计 "对抗" 位置 False 的次数

# 遍历文件夹中的所有文件
for filename in os.listdir(folder_path):
    if filename.endswith(".txt"):
        # 假设文件名格式是 0_成功Y_对抗Z.txt
        parts = filename.split('_')

        # 统计 "成功" 位置 (Y) 和 "对抗" 位置 (Z) 的 True 和 False
        success_status = parts[1][2:]  # "成功" 后面的 True 或 False
        confront_status = parts[2][2:].replace('.txt', '')  # "对抗" 后面的 True 或 False

        if success_status == "True":
            success_true_count += 1
        elif success_status == "False":
            success_false_count += 1

        if confront_status == "True":
            confront_true_count += 1
        elif confront_status == "False":
            confront_false_count += 1

# 输出结果
print(f"成功位置 True 的次数: {success_true_count}")
print(f"成功位置 False 的次数: {success_false_count}")
print(f"对抗位置 True 的次数: {confront_true_count}")
print(f"对抗位置 False 的次数: {confront_false_count}")
print(f"成功率: {success_true_count / (success_true_count + success_false_count) * 100:.2f}%,"
      f"对抗胜率: {confront_true_count / (confront_true_count + confront_false_count) * 100:.2f}%")