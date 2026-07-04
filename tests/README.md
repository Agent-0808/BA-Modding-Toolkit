# BAMT tests

本目录用于存储BA Modding Toolkit的测试用例

## 需要提供的文件

为了运行完整的测试，需要在`assets/`目录下提供以下文件：

### `assets/bundles/`
- `*.bundle`

用于测试读取、保存、资源提取等

### `assets/mod_update/`
- `old/*.bundle`
- `new/*.bundle`

用于测试mod更新功能

### `assets/packer/`
- `*.bundle`
- `*.png`
- `*.atlas`
- `*.skel`

用于测试packer功能

### `assets/spine/`
- `old_assets/*.skel`
- `old_assets/*.atlas`
- `old_assets/*.png`
- `old_assets/*2.png`
- `new_bundle/*.bundle`

用于测试spine功能的重命名和打包

*注：如果不提供文件，也可以运行不需要这些文件的测试用例，会跳过需要文件的测试用例*

## 运行

```bash
uv run pytest -v
```