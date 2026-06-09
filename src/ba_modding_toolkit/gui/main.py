# gui/main.py

from .utils import tbDnDWindow
from .app import App

def main():
    root = tbDnDWindow(themename='cosmo')
    app = App(root)
    print("BA Modding Toolkit 已启动")

    root.mainloop()