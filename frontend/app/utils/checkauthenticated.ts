export default async function isAuthenticated() {
  const res = await fetch('/api/checkauth', {
    method: 'POST',
    signal: AbortSignal.timeout(5000),
    credentials: 'include',
  });

  return res.status == 200;
}
