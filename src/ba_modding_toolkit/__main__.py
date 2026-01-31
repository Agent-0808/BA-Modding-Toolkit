# __main__.py

try:
    from . import gui
    print("from . import gui")
except ImportError:
    import ba_modding_toolkit.gui as gui
    print("import ba_modding_toolkit.gui as gui")

if __name__ == "__main__":
    gui.main()
