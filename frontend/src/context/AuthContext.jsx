import React, { createContext, useContext, useState, useEffect } from 'react';
import { authService } from '../services/authService';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [owner, setOwner] = useState(() => authService.getCachedProfile());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const verifyAuth = async () => {
      try {
        const profile = await authService.getProfile();
        if (mounted) {
          setOwner(profile);
        }
      } catch (err) {
        if (mounted) {
          // If session expired or cookie not present
          setOwner(null);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    verifyAuth();
    return () => {
      mounted = false;
    };
  }, []);

  const login = async (email, password) => {
    const res = await authService.login(email, password);
    const profile = { owner_id: res.owner_id, name: res.name, email: res.email };
    setOwner(profile);
    return res;
  };

  const register = async (name, email, password) => {
    const res = await authService.register(name, email, password);
    const profile = { owner_id: res.owner_id, name: res.name, email: res.email };
    setOwner(profile);
    return res;
  };

  const logout = async () => {
    await authService.logout();
    setOwner(null);
  };

  return (
    <AuthContext.Provider value={{ owner, loading, login, register, logout, isAuthenticated: Boolean(owner) }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
