// static/js/auth.js
// 统一的登录状态管理

const Auth = {
    // 检查登录状态
    async checkLoginStatus() {
        try {
            console.log('正在检查登录状态...');
            
            // 从localStorage获取session_id
            const sessionId = this.getLocalSessionId();
            
            const res = await fetch('/api/check-login', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': sessionId ? `Session ${sessionId}` : ''
                },
                credentials: 'include'
            });
            
            if (!res.ok) {
                console.error('登录状态检查失败:', res.status);
                // 如果API失败，尝试从localStorage恢复
                const localUser = this.getLocalUser();
                if (localUser) {
                    return { isLogin: true, user: localUser };
                }
                return { isLogin: false, user: {} };
            }
            
            const data = await res.json();
            console.log('登录状态响应:', data);
            
            // 如果服务器返回未登录，但localStorage有数据，仍然使用localStorage
            if (!data.isLogin) {
                const localUser = this.getLocalUser();
                if (localUser) {
                    console.log('使用localStorage的用户信息:', localUser);
                    return { isLogin: true, user: localUser };
                }
            }
            
            return {
                isLogin: data.isLogin || false,
                user: data.user || {}
            };
        } catch (error) {
            console.error('检查登录状态失败:', error);
            // 出错时尝试从localStorage恢复
            const localUser = this.getLocalUser();
            if (localUser) {
                return { isLogin: true, user: localUser };
            }
            return { isLogin: false, user: {} };
        }
    },

    // 登出
    async logout() {
        try {
            // 从localStorage获取session_id
            const sessionId = this.getLocalSessionId();
            
            const res = await fetch('/api/logout', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': sessionId ? `Session ${sessionId}` : ''
                },
                credentials: 'include'
            });
            
            const data = await res.json();
            console.log('登出响应:', data);
            
            this.clearLoginInfo();
            return { success: true, message: data.msg || '退出成功' };
        } catch (error) {
            console.error('登出失败:', error);
            this.clearLoginInfo();
            return { success: true, message: '已清除本地登录状态' };
        }
    },

    // 保存登录信息到localStorage
    saveLoginInfo(sessionId, userInfo) {
        if (sessionId) {
            localStorage.setItem('session_id', sessionId);
            console.log('保存session_id到localStorage:', sessionId);
        }
        if (userInfo) {
            localStorage.setItem('user_info', JSON.stringify(userInfo));
            console.log('保存用户信息到localStorage:', userInfo);
        }
    },

    // 清除登录信息
    clearLoginInfo() {
        localStorage.removeItem('session_id');
        localStorage.removeItem('user_info');
        console.log('已清除本地存储');
    },

    // 获取本地用户信息
    getLocalUser() {
        try {
            const userStr = localStorage.getItem('user_info');
            return userStr ? JSON.parse(userStr) : null;
        } catch {
            return null;
        }
    },

    // 获取本地sessionId
    getLocalSessionId() {
        return localStorage.getItem('session_id');
    }
};