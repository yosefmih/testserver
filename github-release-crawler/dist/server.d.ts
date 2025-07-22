#!/usr/bin/env node
declare const app: import("express-serve-static-core").Express;
declare module 'express-serve-static-core' {
    interface Request {
        requestId: string;
    }
}
export default app;
//# sourceMappingURL=server.d.ts.map