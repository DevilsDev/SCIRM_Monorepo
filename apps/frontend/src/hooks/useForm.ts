import { useState, useCallback, ChangeEvent } from 'react';

// Validator types
type ValidatorFn = (value: any, values?: any) => string | undefined;

export const validators = {
  required: (msg = 'This field is required'): ValidatorFn => (value) =>
    (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) ? msg : undefined,

  minLength: (n: number, msg?: string): ValidatorFn => (value) =>
    typeof value === 'string' && value.length < n ? (msg || `Minimum ${n} characters`) : undefined,

  maxLength: (n: number, msg?: string): ValidatorFn => (value) =>
    typeof value === 'string' && value.length > n ? (msg || `Maximum ${n} characters`) : undefined,

  min: (n: number, msg?: string): ValidatorFn => (value) =>
    typeof value === 'number' && value < n ? (msg || `Minimum value is ${n}`) : undefined,

  max: (n: number, msg?: string): ValidatorFn => (value) =>
    typeof value === 'number' && value > n ? (msg || `Maximum value is ${n}`) : undefined,

  pattern: (regex: RegExp, msg = 'Invalid format'): ValidatorFn => (value) =>
    typeof value === 'string' && value && !regex.test(value) ? msg : undefined,

  email: (msg = 'Invalid email address'): ValidatorFn => (value) =>
    typeof value === 'string' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? msg : undefined,

  custom: (fn: (value: any, values?: any) => string | undefined): ValidatorFn => fn,
};

interface UseFormOptions<T> {
  initialValues: T;
  validators?: Partial<Record<keyof T, ValidatorFn[]>>;
  onSubmit: (values: T) => Promise<void> | void;
}

export function useForm<T extends Record<string, any>>({ initialValues, validators: fieldValidators = {}, onSubmit }: UseFormOptions<T>) {
  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});
  const [touched, setTouched] = useState<Partial<Record<keyof T, boolean>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validateField = useCallback((name: keyof T, value: any): string | undefined => {
    const fieldRules = fieldValidators[name];
    if (!fieldRules) return undefined;
    for (const rule of fieldRules) {
      const error = rule(value, values);
      if (error) return error;
    }
    return undefined;
  }, [fieldValidators, values]);

  const validateAll = useCallback((): Partial<Record<keyof T, string>> => {
    const newErrors: Partial<Record<keyof T, string>> = {};
    for (const key of Object.keys(fieldValidators) as (keyof T)[]) {
      const error = validateField(key, values[key]);
      if (error) newErrors[key] = error;
    }
    return newErrors;
  }, [fieldValidators, values, validateField]);

  const setFieldValue = useCallback((name: keyof T, value: any) => {
    setValues((prev) => ({ ...prev, [name]: value }));
    // Clear error on change
    setErrors((prev) => {
      const next = { ...prev };
      delete next[name];
      return next;
    });
  }, []);

  const handleChange = useCallback((e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    const finalValue = type === 'number' ? (value === '' ? '' : Number(value)) : value;
    setFieldValue(name as keyof T, finalValue);
  }, [setFieldValue]);

  const handleBlur = useCallback((e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name } = e.target;
    setTouched((prev) => ({ ...prev, [name]: true }));
    const error = validateField(name as keyof T, values[name as keyof T]);
    if (error) {
      setErrors((prev) => ({ ...prev, [name]: error }));
    }
  }, [validateField, values]);

  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const newErrors = validateAll();
    setErrors(newErrors);
    // Mark all as touched
    const allTouched: Partial<Record<keyof T, boolean>> = {};
    for (const key of Object.keys(values) as (keyof T)[]) allTouched[key] = true;
    setTouched(allTouched);

    if (Object.keys(newErrors).length > 0) return;

    setIsSubmitting(true);
    try {
      await onSubmit(values);
    } finally {
      setIsSubmitting(false);
    }
  }, [validateAll, values, onSubmit]);

  const reset = useCallback((newValues?: T) => {
    setValues(newValues || initialValues);
    setErrors({});
    setTouched({});
    setIsSubmitting(false);
  }, [initialValues]);

  const isValid = Object.keys(validateAll()).length === 0;

  return {
    values,
    errors,
    touched,
    isSubmitting,
    isValid,
    handleChange,
    handleBlur,
    handleSubmit,
    setFieldValue,
    reset,
  };
}
