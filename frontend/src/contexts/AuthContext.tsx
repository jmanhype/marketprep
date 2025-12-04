/**
 * Authentication context provider.
 *
 * Manages:
 * - Login/logout
 * - Token storage
 * - Current vendor state
 * - Authentication status
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from 'react';
import { apiClient } from '../lib/api-client';

/**
 * Vendor interface from backend.
 */
export interface Vendor {
  id: string;
  email: string;
  business_name: string;
  subscription_tier: string;
  subscription_status: string;
}

/**
 * Login response from backend.
 */
interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  vendor: Vendor;
}

/**
 * Registration response from backend.
 */
interface RegisterResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  vendor: Vendor;
}

/**
 * Auth context interface.
 */
interface AuthContextType {
  vendor: Vendor | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, businessName: string) => Promise<void>;
  updateVendorProfile: (vendor: Vendor) => void;
  logout: () => void;
}

/**
 * Auth context.
 */
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Auth provider props.
 */
interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Auth context provider component.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  /**
   * Check if user is authenticated on mount.
   */
  useEffect(() => {
    const checkAuth = async () => {
      console.log('[AuthContext] Checking auth...');
      const accessToken = localStorage.getItem('access_token');
      console.log('[AuthContext] Has access token:', !!accessToken);

      if (!accessToken) {
        console.log('[AuthContext] No token found, setting loading false');
        setIsLoading(false);
        return;
      }

      try {
        console.log('[AuthContext] Calling /api/v1/vendors/me');
        // Verify token by fetching vendor profile
        // This will use the token from localStorage via apiClient interceptor
        const response = await apiClient.get<Vendor>('/api/v1/vendors/me');
        console.log('[AuthContext] Auth check successful, vendor:', response.business_name);
        setVendor(response);
      } catch (error: any) {
        console.error('[AuthContext] Auth check error:', error.response?.status, error.message);
        // Only clear tokens on authentication errors (401), not network errors
        if (error.response?.status === 401) {
          console.log('[AuthContext] 401 error - clearing tokens');
          // Token invalid or expired - clear storage
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('vendor_email');
          setVendor(null);
        } else {
          console.log('[AuthContext] Non-401 error - treating as temporarily authenticated');
          // For network/CORS errors, create a minimal vendor object so user isn't logged out
          // The vendor profile will be fetched successfully on the next API call
          const storedVendorEmail = localStorage.getItem('vendor_email');
          if (storedVendorEmail) {
            // Use cached vendor data if available
            setVendor({
              id: '', // Will be updated on next successful API call
              email: storedVendorEmail,
              business_name: 'Loading...',
              subscription_tier: 'free',
              subscription_status: 'active',
            });
          }
          // Schedule a retry after a short delay
          setTimeout(() => {
            apiClient.get<Vendor>('/api/v1/vendors/me')
              .then(response => {
                console.log('[AuthContext] Retry successful, vendor:', response.business_name);
                setVendor(response);
              })
              .catch(retryError => {
                console.error('[AuthContext] Retry failed:', retryError.message);
              });
          }, 2000); // Retry after 2 seconds
        }
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  /**
   * Login with email and password.
   */
  const login = async (email: string, password: string): Promise<void> => {
    try {
      const response = await apiClient.post<LoginResponse>(
        '/api/v1/auth/login',
        {
          email,
          password,
        }
      );

      // Store tokens
      localStorage.setItem('access_token', response.access_token);
      localStorage.setItem('refresh_token', response.refresh_token);

      // Cache vendor email for offline/error fallback
      localStorage.setItem('vendor_email', response.vendor.email);

      // Set vendor
      setVendor(response.vendor);
    } catch (error: any) {
      // Re-throw with user-friendly message
      const errorMessage = error.response?.data?.detail || error.response?.data?.message;

      if (error.response?.status === 401) {
        throw new Error('Invalid email or password');
      }

      throw new Error(
        errorMessage || 'Login failed. Please try again.'
      );
    }
  };

  /**
   * Register new vendor account.
   */
  const register = async (
    email: string,
    password: string,
    businessName: string
  ): Promise<void> => {
    try {
      const response = await apiClient.post<RegisterResponse>(
        '/api/v1/auth/register',
        {
          email,
          password,
          business_name: businessName,
        }
      );

      // Store tokens
      localStorage.setItem('access_token', response.access_token);
      localStorage.setItem('refresh_token', response.refresh_token);

      // Cache vendor email for offline/error fallback
      localStorage.setItem('vendor_email', response.vendor.email);

      // Set vendor
      setVendor(response.vendor);
    } catch (error: any) {
      // Re-throw with user-friendly message
      const errorMessage = error.response?.data?.detail || error.response?.data?.message;

      if (error.response?.status === 400 && errorMessage?.includes('already registered')) {
        throw new Error('An account with this email already exists');
      }

      throw new Error(
        errorMessage || 'Registration failed. Please try again.'
      );
    }
  };

  /**
   * Update vendor profile in context.
   */
  const updateVendorProfile = (updatedVendor: Vendor): void => {
    setVendor(updatedVendor);
  };

  /**
   * Logout user.
   */
  const logout = (): void => {
    // Clear tokens and cached data
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('vendor_email');

    // Clear vendor
    setVendor(null);

    // Redirect to login
    window.location.href = '/auth/login';
  };

  const value: AuthContextType = {
    vendor,
    isAuthenticated: vendor !== null,
    isLoading,
    login,
    register,
    updateVendorProfile,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to use auth context.
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
