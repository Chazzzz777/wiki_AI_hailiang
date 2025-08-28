const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: `http://${process.env.REACT_APP_HOSTNAME || 'localhost'}:${process.env.REACT_APP_BACKEND_PORT || 5001}`,
      changeOrigin: true,
    })
  );
};