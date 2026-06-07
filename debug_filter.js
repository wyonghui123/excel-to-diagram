// 检查 v2 API 返回的数据
const response = await fetch('http://localhost:3010/api/v2/meta/user_group/view-config/default');
const data = await response.json();

if (data.data && data.data.list) {
  const columns = data.data.list.columns;
  console.log('v2 API columns:', columns.length);
  console.log('parent_id column:', columns.find(c => c.key === 'parent_id'));
} else {
  console.log('v2 API response keys:', Object.keys(data.data || {}));
}
