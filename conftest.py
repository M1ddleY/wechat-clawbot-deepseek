"""pytest 根配置：将项目根加入 sys.path（嵌入式 Python 的 _pth 会固定 sys.path）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
