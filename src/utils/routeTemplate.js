const DEFAULT_TEMPLATES = {
  object_list: '/objects/{primary_object_type}',
  object_detail: '/objects/{primary_object_type}/{id}',
  multi_object_hub: '/{menu_code}',
  custom_page: '/{menu_code}',
  dashboard: '/{menu_code}',
}

export function resolveRoutePath(menu) {
  if (menu.menu_path) return menu.menu_path

  const template = menu.route_template || DEFAULT_TEMPLATES[menu.page_type]

  if (!template) {
    return `/${(menu.menu_code || menu.primary_object_type || 'unknown').replace(/_/g, '-')}`
  }

  return template
    .replace(/\{primary_object_type\}/g, menu.primary_object_type || '')
    .replace(/\{menu_code\}/g, menu.menu_code || '')
    .replace(/\{id\}/g, ':id')
    .replace(/_/g, '-')
}
