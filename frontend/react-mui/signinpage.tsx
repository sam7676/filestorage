import * as React from 'react';
import { AppProvider } from '@toolpad/core/AppProvider';
import { AuthResponse, SignInPage, type AuthProvider } from '@toolpad/core/SignInPage';
import { useTheme } from '@mui/material/styles';

// preview-start
const providers = [{ id: 'credentials', name: 'Email and Password' }];
// preview-end

export default function CredentialsSignInPage(
  signIn:
    | ((
        provider: AuthProvider,
        formData?: any,
        callbackUrl?: string,
      ) => void | Promise<AuthResponse> | undefined)
    | undefined,
) {
  const theme = useTheme();
  return (
    // preview-start
    <AppProvider theme={theme}>
      <SignInPage
        signIn={signIn}
        providers={providers}
        slotProps={{ emailField: { autoFocus: false }, form: { noValidate: true } }}
      />
    </AppProvider>
    // preview-end
  );
}
