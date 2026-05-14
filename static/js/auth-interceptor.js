// static/js/auth-interceptor.js
// 登录状态拦截器，自动处理401未授权

(function() {
    // 保存原始的fetch
    const originalFetch = window.fetch;
    
    // 需要拦截的API路径
    const PROTECTED_PATHS = [
        '/api/talk/add',
        '/api/talk/delete',
        '/api/logout'
    ];
    
    // 重写fetch
    window.fetch = async function(url, options = {}) {
        // 检查是否是受保护的API
        const isProtected = PROTECTED_PATHS.some(path => url.includes(path));
        
        // 添加认证头
        if (isProtected) {
            const sessionId = Auth.getLocalSessionId();
            if (sessionId) {
                options.headers = {
                    ...options.headers,
                    'Authorization': `Session ${sessionId}`
                };
            }
            options.credentials = 'include';
        }
        
        try {
            const response = await originalFetch(url, options);
            
            // 处理401未授权
            if (response.status === 401) {
                const data = await response.clone().json().catch(() => ({}));
                if (data.need_login || data.code === 401) {
                    Auth.clearLoginInfo();
                    
                    // 保存当前页面，登录后跳回
                    const currentPath = window.location.pathname;
                    if (!currentPath.includes('/login/')) {
                        window.location.href = `/login/index.html?redirect=${encodeURIComponent(currentPath)}`;
                    }
                }
                return response;
            }
            
            return response;
        } catch (error) {
            console.error('请求失败:', error);
            throw error;
        }
    };
    
    // 添加全局错误处理
    window.addEventListener('unhandledrejection', function(event) {
        console.error('未处理的Promise错误:', event.reason);
    });
})();