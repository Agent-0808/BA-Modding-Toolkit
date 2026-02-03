# __main__.py - CLI 模块入口点

try:
    from . import main
except ImportError:
    import ba_modding_toolkit.cli.main as main

if __name__ == "__main__":
    main.main()