/**
 * Frontend monitoring and error tracking
 * Optional Sentry integration for error reporting
 */

let sentryInitialized = false;

/**
 * Initialize Sentry for frontend error tracking
 * Only runs if NEXT_PUBLIC_SENTRY_DSN is set
 */
export function initSentry() {
  if (sentryInitialized) return;

  const sentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  const sentryEnabled = process.env.NEXT_PUBLIC_SENTRY_ENABLED === 'true';

  if (!sentryEnabled || !sentryDsn) {
    console.info('Sentry frontend tracking is disabled');
    return;
  }

  try {
    // Dynamic import to avoid bundling if not used
    import('@sentry/nextjs').then((Sentry) => {
      Sentry.init({
        dsn: sentryDsn,
        environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || 'production',
        tracesSampleRate: parseFloat(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE || '0.1'),

        // Don't send PII
        beforeSend(event) {
          // Remove sensitive data
          if (event.request) {
            delete event.request.cookies;
          }
          return event;
        },

        // Ignore common errors
        ignoreErrors: [
          'ResizeObserver loop limit exceeded',
          'Non-Error promise rejection captured',
        ],
      });

      sentryInitialized = true;
      console.info('Sentry frontend tracking initialized');
    }).catch((error) => {
      console.warn('Failed to load Sentry SDK:', error);
    });
  } catch (error) {
    console.warn('Sentry initialization failed:', error);
  }
}

/**
 * Track a custom error
 */
export function trackError(error: Error, context?: Record<string, any>) {
  console.error('Error:', error, context);

  if (sentryInitialized && typeof window !== 'undefined') {
    import('@sentry/nextjs').then((Sentry) => {
      if (context) {
        Sentry.withScope((scope) => {
          Object.entries(context).forEach(([key, value]) => {
            scope.setExtra(key, value);
          });
          Sentry.captureException(error);
        });
      } else {
        Sentry.captureException(error);
      }
    }).catch(() => {
      // Silently fail if Sentry not available
    });
  }
}

/**
 * Track a custom event/message
 */
export function trackEvent(message: string, level: 'info' | 'warning' | 'error' = 'info') {
  console[level](message);

  if (sentryInitialized && typeof window !== 'undefined') {
    import('@sentry/nextjs').then((Sentry) => {
      Sentry.captureMessage(message, level);
    }).catch(() => {
      // Silently fail if Sentry not available
    });
  }
}
