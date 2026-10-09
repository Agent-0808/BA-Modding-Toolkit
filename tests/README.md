# BAMT tests

本目录用于存储BA Modding Toolkit的测试用例

## 需要提供的文件

为了运行完整的测试，需要在`assets/`目录下提供以下文件。
目录按数据扮演的**角色**命名，不绑定具体角色素材；每组下按**案例子目录**组织，
案例由 conftest 自动发现并按参数化逐案例运行——新增多组数据只需复制案例目录，无需改代码：

### `assets/sample/<case>/`
- `assets/*.png`
- `assets/*.atlas`
- `assets/*.skel`
- `bundles/*.bundle`

主力组：测试 bundle 读取、保存、资源提取、packer 打包、CRC、文件名搜索、atlas 操作等

### `assets/mod_update/<case>/`
- `old/*.bundle`
- `new/*.bundle`

更新对组：测试 mod 更新功能、CLI update、core 搜索、多 bundle 提取

*注：`old/`与`new/`的 bundle 文件名必须保持完整的游戏命名格式（可被`parse_filename`解析），新旧语义用子目录区分*

### `assets/legacy_rename/<case>/`
- `assets/*.png`
- `assets/*.atlas`
- `assets/*.skel`
- `bundles/*.bundle`

legacy 重命名组：测试磁盘旧命名文件（如`XXX2.png`）与 bundle 内名（如`XXX_2`）不匹配时的重命名和打包

### `assets/ress_regress/<case>/`
- `mod/*.bundle`
- `original/*.bundle`

流引用回归组：测试 mod update 后`.resS`/`.resource`流引用闭合

*注：不提供文件时，引用案例数据的测试会以空参数集自动跳过*
