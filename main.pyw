# main.py

from tkinterdnd2 import TkinterDnD
import ttkbootstrap as tb
from ui import App

if __name__ == "__main__":
    # 先创建 TkinterDnD 窗口
    root = TkinterDnD.Tk()
    # 应用 ttkbootstrap 样式
    tb.Style(theme='cosmo')
    
    # 创建并运行应用
    app = App(root)
    print("BA Modding Toolkit 已启动")
    
    # 启动 Tkinter 事件循环
    root.mainloop()