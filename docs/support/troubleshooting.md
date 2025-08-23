# Troubleshooting Guide

This guide helps resolve common issues with the SCIRM platform.

## Common Issues

### Authentication Problems

**Issue**: Unable to log in to the dashboard
**Solution**:
1. Verify your credentials are correct
2. Check if your account has been activated
3. Clear browser cache and cookies
4. Contact your system administrator

**Issue**: Session expires frequently
**Solution**:
1. Check your network connection stability
2. Verify system time is synchronized
3. Contact support if issue persists

### Performance Issues

**Issue**: Slow response times
**Solution**:
1. Check your internet connection speed
2. Verify system load in the monitoring dashboard
3. Clear browser cache
4. Try accessing during off-peak hours

**Issue**: Dashboard not loading
**Solution**:
1. Refresh the browser page
2. Check browser console for JavaScript errors
3. Verify you're using a supported browser
4. Disable browser extensions temporarily

### Data Issues

**Issue**: Missing or outdated risk assessments
**Solution**:
1. Check data source connections
2. Verify data ingestion pipelines are running
3. Review system status page
4. Contact support with specific timestamps

**Issue**: Incorrect risk scores
**Solution**:
1. Verify input data quality
2. Check model configuration settings
3. Review recent system updates
4. Submit feedback through the dashboard

## System Status

Check the current system status at: [System Status Page]

## Browser Support

SCIRM supports the following browsers:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Getting Help

If you can't resolve an issue:

1. Check the [FAQ](faq.md) for common questions
2. Review the [User Guide](../intro/getting-started.md)
3. Contact support via [Support Channels](contact.md)

## Error Codes

### HTTP Error Codes
- **400**: Bad Request - Check your input parameters
- **401**: Unauthorized - Authentication required
- **403**: Forbidden - Insufficient permissions
- **404**: Not Found - Resource doesn't exist
- **500**: Internal Server Error - Contact support

### Application Error Codes
- **SCIRM-001**: Data ingestion failure
- **SCIRM-002**: Model inference timeout
- **SCIRM-003**: Database connection error
- **SCIRM-004**: Authentication service unavailable

---

*For additional support, contact the SCIRM support team.*
