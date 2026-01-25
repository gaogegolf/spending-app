'use client';

import { useMemo } from 'react';

interface PasswordStrengthIndicatorProps {
  password: string;
}

interface Requirement {
  label: string;
  met: boolean;
}

export default function PasswordStrengthIndicator({ password }: PasswordStrengthIndicatorProps) {
  const requirements: Requirement[] = useMemo(() => [
    { label: 'At least 8 characters', met: password.length >= 8 },
    { label: 'Contains uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'Contains lowercase letter', met: /[a-z]/.test(password) },
    { label: 'Contains number', met: /[0-9]/.test(password) },
    { label: 'Contains special character', met: /[!@#$%^&*(),.?":{}|<>]/.test(password) },
  ], [password]);

  const strength = useMemo(() => {
    const metCount = requirements.filter(r => r.met).length;
    if (metCount <= 1) return { level: 0, label: 'Very Weak', color: 'bg-red-500' };
    if (metCount === 2) return { level: 1, label: 'Weak', color: 'bg-orange-500' };
    if (metCount === 3) return { level: 2, label: 'Fair', color: 'bg-yellow-500' };
    if (metCount === 4) return { level: 3, label: 'Good', color: 'bg-blue-500' };
    return { level: 4, label: 'Strong', color: 'bg-green-500' };
  }, [requirements]);

  if (!password) return null;

  return (
    <div className="mt-2 space-y-2">
      {/* Strength bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 flex gap-1">
          {[0, 1, 2, 3].map((index) => (
            <div
              key={index}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                index <= strength.level ? strength.color : 'bg-gray-200'
              }`}
            />
          ))}
        </div>
        <span className={`text-xs font-medium ${
          strength.level <= 1 ? 'text-red-600' :
          strength.level === 2 ? 'text-yellow-600' :
          strength.level === 3 ? 'text-blue-600' :
          'text-green-600'
        }`}>
          {strength.label}
        </span>
      </div>

      {/* Requirements checklist */}
      <ul className="space-y-1">
        {requirements.map((req, index) => (
          <li key={index} className="flex items-center gap-1.5 text-xs">
            {req.met ? (
              <svg className="w-3.5 h-3.5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-3.5 h-3.5 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="2" fill="none" />
              </svg>
            )}
            <span className={req.met ? 'text-green-700' : 'text-gray-500'}>
              {req.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
