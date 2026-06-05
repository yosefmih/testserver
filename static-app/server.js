const Koa = require('koa');
const serve = require('koa-static');
const send = require('koa-send');
const path = require('path');

const app = new Koa();

app.use((ctx, next) => {
  if (ctx.request.path === '/healthz') {
    ctx.status = 200;
    ctx.body = 'ok';
    return Promise.resolve();
  }
  return next();
});

app.use(serve(path.join(__dirname, 'build')));

app.use((ctx) => {
  const pathname = ctx.request.url.split('?')[0];
  if (/\.[^/]+$/.test(pathname) && !pathname.endsWith('.html')) {
    ctx.status = 404;
    return;
  }
  ctx.status = 200;
  return send(ctx, path.join('build', 'index.html'));
});

const port = process.env.PORT || 3000;
app.listen(port, '0.0.0.0', () => {
  console.info(`static-app listening on ${port}; build=${process.env.BUILD_ID || 'unknown'}`);
});
