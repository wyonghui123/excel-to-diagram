# 401 认证错误解决方案

## 🎯 问题诊断结果

✅ **所有检查项都正常**：
- ✅ 数据库文件存在
- ✅ 用户数据正常（找到 5 个用户）
- ✅ JWT_SECRET_KEY 已配置
- ✅ 后端服务正在运行（端口 5000）
- ✅ Token 创建成功

## 🔧 解决方案

### 方法一：重新登录（推荐）

1. **打开前端应用**
2. **清除浏览器缓存**：
   - 按 F12 打开开发者工具
   - 切换到 Application 标签
   - 找到 Local Storage
   - 删除 `auth_token` 和 `auth_user`

3. **重新登录**：
   - 用户名：`admin`
   - 密码：`admin123`

### 方法二：手动设置 Token

如果重新登录不成功，可以手动设置 Token：

1. **打开浏览器开发者工具**（F12）
2. **切换到 Console 标签**
3. **执行以下命令**：

```javascript
// 设置 Token
localStorage.setItem('auth_token', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJjZDUwNWU4NWI2YzFlN2IwYjI5ZjllYWQzZmM2MjEyMyIsInVzZXJfaWQiOjEsInVzZXJuYW1lIjoiYWRtaW4iLCJkaXNwbGF5X25hbWUiOiJcdTdiYTFcdTc0MDZcdTU0NTgiLCJyb2xlcyI6WyJhZG1pbiIsInRlc3QiXSwicGVybWlzc2lvbnMiOlsiKiJdLCJleHAiOjE3NzgzNDkzNjEsImlhdCI6MTc3ODMzNDk2MX0.tStCx2_6XJOtJayccUAW6Ey6P1VAQ-JZ_dMqw5KCpNA');

// 设置用户信息
localStorage.setItem('auth_user', JSON.stringify({
  user_id: 1,
  username: "admin",
  display_name: "管理员",
  email: "admin@example.com",
  roles: ["admin", "test"],
  permissions: ["*"]
}));

// 刷新页面
location.reload();
```

### 方法三：检查前端代码

如果上述方法都不行，检查前端代码：

1. **检查 API 请求头**：
```javascript
// 确保请求头包含 Authorization
headers: {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
}
```

2. **检查 Token 是否正确获取**：
```javascript
// 在浏览器控制台执行
console.log('Token:', localStorage.getItem('auth_token'));
console.log('User:', localStorage.getItem('auth_user'));
```

## 📝 常见问题

### Q1: Token 过期了怎么办？

**A**: Token 有效期为 4 小时。过期后需要重新登录或重新生成 Token。

### Q2: 为什么会出现 401 错误？

**A**: 可能的原因：
- Token 过期
- Token 无效
- Token 未正确传递
- 后端服务重启导致密钥变化

### Q3: 如何验证 Token 是否有效？

**A**: 在浏览器控制台执行：
```javascript
// 解码 Token（不验证签名）
const token = localStorage.getItem('auth_token');
const payload = JSON.parse(atob(token.split('.')[1]));
console.log('Token payload:', payload);
console.log('Expired:', new Date(payload.exp * 1000) < new Date());
```

## 🚀 快速测试

运行以下命令测试 API：

```bash
# 使用 admin 用户登录
curl -X POST http://127.0.0.1:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 使用返回的 token 测试 API
curl -X GET http://127.0.0.1:5000/api/v1/users \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## ✅ 验证成功

如果能看到用户列表，说明问题已解决！

---

**创建时间**：2026-05-09  
**Token 过期时间**：2026-05-09 17:56:01  
**管理员账号**：admin / admin123
