import { cookies } from 'next/headers';
import { redirect, RedirectType } from 'next/navigation';


export default async function IndexPage({ searchParams }: { searchParams: { view?: string } }) {
    const params = await searchParams;
    const view = params.view || 'upload';

    const cookieStore = await cookies();
    const accessToken = cookieStore.get('access_token');
    const refreshToken = cookieStore.get('refresh_token');

    if (!accessToken || !refreshToken) {

        redirect('/login', RedirectType.push)
    }

    switch (view) {
        case 'upload':

            redirect('/upload', RedirectType.push)
        case 'view':
            redirect('/view', RedirectType.push)
        default:
            redirect('/view', RedirectType.push)
    }
}