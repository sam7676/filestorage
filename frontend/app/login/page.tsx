'use client';

import { AuthProvider } from '@toolpad/core';
import CredentialsSignInPage from '../../react-mui/signinpage';
import crypto from 'crypto';
import { redirect, RedirectType } from 'next/navigation'
import isAuthenticated from '../utils/checkauthenticated';

const signIn: (formData: FormData) => void = async (
    formData,
) => {

    process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";

    const email = formData.get('email');
    formData.delete('email');
    formData.set('username', email?.toString() || '');

    const password = formData.get('password');

    const hashedPassword = hashPassword(password?.toString() || '');

    formData.set('password', hashedPassword);

    const res = await fetch('/api/token', {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(20000),
        credentials: 'include'
    });

    if (!res.ok) {
        throw new Error('Login failed')
    };

    redirect('/', RedirectType.push)
};

export default function Login() {

    const signInClient: (provider: AuthProvider, formData: FormData) => void = async (
        provider,
        formData,
    ) => {
        signIn(formData);
    }


    return <div>
        {CredentialsSignInPage(signInClient)}
    </div>
}




function hashPassword(password: crypto.BinaryLike) {
    const salt = "helloworld";
    const iterations = 1000;
    const keylen = 64;
    const digest = 'sha512';

    const hash = crypto.pbkdf2Sync(password, salt, iterations, keylen, digest).toString('hex');

    return hash
}
