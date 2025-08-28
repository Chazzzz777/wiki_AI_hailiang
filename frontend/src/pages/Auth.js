import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spin, Typography } from 'antd';
import apiClient from '../utils/api';
import './Auth.css';

const { Title, Text } = Typography;

const Auth = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('user_access_token');
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    
    // 移除从根路径重定向到/auth路径的逻辑，确保redirect_uri一致
    
    // 写死重定向到根路径，确保与飞书应用配置一致
    const REDIRECT_URI = `http://${process.env.REACT_APP_HOSTNAME || 'localhost'}:${process.env.REACT_APP_FRONTEND_PORT || 3001}`;

    if (token) {
      navigate('/wiki');
      return;
    }

    if (code) {
      // 打印授权相关信息
      console.log('=== 授权回调信息 ===');
      console.log('授权码:', code);
      console.log('重定向URI:', REDIRECT_URI);
      console.log('后端URL:', process.env.REACT_APP_BACKEND_URL);
      console.log('前端端口:', process.env.REACT_APP_FRONTEND_PORT);
      console.log('主机名:', process.env.REACT_APP_HOSTNAME);
      console.log('==================');
      
      apiClient.post('/api/auth/token', { code, redirect_uri: REDIRECT_URI })
        .then(response => {
          console.log('授权请求成功:', response.data);
          const { user_access_token } = response.data;
          if (user_access_token) {
            localStorage.setItem('user_access_token', user_access_token);
            navigate('/wiki');
          } else {
            console.error('未能从响应中获取授权令牌:', response.data);
            setError('未能从响应中获取授权令牌。');
            setLoading(false);
          }
        })
        .catch(err => {
          console.error('授权请求失败:', err);
          let errorMsg = '无法获取授权，请稍后重试或联系管理员。';
          if (err.response) {
            console.error('授权请求错误响应:', err.response);
            errorMsg = `授权请求失败 [${err.response.status}]: ${JSON.stringify(err.response.data || err.response.statusText)}`;
          } else if (err.message) {
            console.error('授权请求网络错误:', err.message);
            errorMsg = `网络错误: ${err.message}`;
          }
          setError(errorMsg);
          setLoading(false);
        });
    } else {
      const APP_ID = process.env.REACT_APP_FEISHU_APP_ID;
      const scope = 'docx:document:readonly wiki:node:move wiki:node:retrieve wiki:space:read wiki:space:retrieve wiki:node:read wiki:wiki:readonly';
      const encodedRedirectUri = encodeURIComponent(REDIRECT_URI);
      window.location.href = `https://open.feishu.cn/open-apis/authen/v1/index?redirect_uri=${encodedRedirectUri}&app_id=${APP_ID}&scope=${scope}`;
    }
  }, [navigate]);

  return (
    <div className="auth-container">
      <div className="auth-card">
        <Title level={3} className="auth-title">知识库管理助手</Title>
        {loading && (
          <>
            <Spin size="large" />
            <p className="auth-tip">正在跳转至飞书授权...</p>
          </>
        )}
        {error && <Text type="danger">{error}</Text>}
      </div>
    </div>
  );
};

export default Auth;