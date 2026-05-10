export function getActiveTenantId(user) {
  if (user?.tenant_id) return user.tenant_id;
  if (typeof window !== 'undefined') return sessionStorage.getItem('um_active_tenant_id') || null;
  return null;
}

export function getActiveTenantName(user) {
  if (typeof window !== 'undefined') return sessionStorage.getItem('um_active_tenant_name') || null;
  return null;
}

export function needsTenantSelection(user) {
  if (!user || user.role !== 'superadmin') return false;
  if (user.tenant_id) return false;
  if (typeof window !== 'undefined') return !sessionStorage.getItem('um_active_tenant_id');
  return true;
}
