import { redirect, RedirectType } from 'next/navigation';

export default async function fetchWithRefresh(url: URL | RequestInfo, requestData: any) {
  const request = new Request(url, requestData);

  var res = await fetch(request);
  if (res.status == 401 || res.status == 403) {
    // Refresh access token and try again
    console.log('Failed fetch');

    await fetch('/api/token/refresh', {
      method: 'POST',
      signal: AbortSignal.timeout(5000),
      credentials: 'include',
    });

    const retryRequest = new Request(url, requestData);

    res = await fetch(retryRequest);

    // We failed twice, clearly the user isn't logged in
    if (res.status == 401 || res.status == 403) {
      redirect('/login', RedirectType.push);
    }
  }

  return res;
}
