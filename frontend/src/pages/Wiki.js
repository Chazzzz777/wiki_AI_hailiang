import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import apiClient from '../utils/api';
import feishuApiClient from '../utils/feishuApiClient';
import { List, Spin, Typography, Button, message, Input, Card, Space, Modal, Empty, Tag } from 'antd';
import { SearchOutlined, CloseOutlined } from '@ant-design/icons';
import InfiniteScroll from 'react-infinite-scroll-component';
import { initCardSpotlight, destroyCardSpotlight } from '../utils/cardSpotlight';
import { initResponsiveGrid, getResponsiveGrid } from '../utils/responsiveGrid';
import { generateCardColor } from '../utils/randomColors';
import { getAnimationManager, getGradientFlowAnimation } from '../utils/animationConfig';
import { getPerformanceMonitor } from '../utils/performanceMonitor';
import './Wiki.css';

const { Title } = Typography;

function Wiki() {
  const navigate = useNavigate();
  const [spaces, setSpaces] = useState([]);

  const [hasMore, setHasMore] = useState(true);
  const [pageToken, setPageToken] = useState(null);
  const loading = useRef(false);
  
  // 搜索相关状态 - 已迁移到新的会话管理系统
  const [searchKeyword, setSearchKeyword] = useState(''); // 搜索关键词输入
  const [isModalOpen, setIsModalOpen] = useState(false); // 搜索结果模态框状态
  
  // 旧的状态变量已被 searchState 和 searchSessionManager 替代：
  // - searchResults -> searchState.results
  // - searchLoading -> searchState.loading
  // - searchHasMore -> searchState.hasMore
  // - searchPageToken -> searchState.pageToken
  // - searchProgress -> searchState.progressInfo
  // - activeSearchIds -> searchState.activeSessions

  // 搜索会话管理器 - 健壮性优化
  const searchSessionManager = useRef({
    sessions: new Map(), // 搜索会话存储
    activeSessionId: null, // 当前活跃的搜索会话
    
    // 创建新的搜索会话
    createSession: (keyword, token = null) => {
      const sessionId = `search_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const session = {
        id: sessionId,
        keyword,
        token,
        status: 'initializing', // initializing, processing, completed, failed, cancelled
        startTime: Date.now(),
        lastUpdateTime: Date.now(),
        progress: {
          total_spaces: 0,
          processed_spaces: 0,
          phase: 'initial',
          elapsed_time: 0
        },
        results: [],
        hasMore: false,
        pageToken: null,
        backendSearchId: null, // 后端返回的搜索ID
        timers: {
          progressCheck: null,
          timeout: null
        },
        retryCount: 0,
        maxRetries: 3
      };
      
      // 清理之前的活跃会话
      if (searchSessionManager.current.activeSessionId) {
        searchSessionManager.current.cleanupSession(searchSessionManager.current.activeSessionId);
      }
      
      searchSessionManager.current.sessions.set(sessionId, session);
      searchSessionManager.current.activeSessionId = sessionId;
      
      return sessionId;
    },
    
    // 获取会话
    getSession: (sessionId) => {
      return searchSessionManager.current.sessions.get(sessionId);
    },
    
    // 更新会话状态
    updateSession: (sessionId, updates) => {
      const session = searchSessionManager.current.getSession(sessionId);
      if (session) {
        Object.assign(session, updates, { lastUpdateTime: Date.now() });
        return session;
      }
      return null;
    },
    
    // 清理会话资源
    cleanupSession: (sessionId) => {
      const session = searchSessionManager.current.getSession(sessionId);
      if (session) {
        // 清理定时器
        if (session.timers.progressCheck) {
          clearInterval(session.timers.progressCheck);
        }
        if (session.timers.timeout) {
          clearTimeout(session.timers.timeout);
        }
        
        // 从会话映射中删除
        searchSessionManager.current.sessions.delete(sessionId);
        
        // 如果是活跃会话，清除活跃状态
        if (searchSessionManager.current.activeSessionId === sessionId) {
          searchSessionManager.current.activeSessionId = null;
        }
      }
    },
    
    // 获取当前活跃会话
    getActiveSession: () => {
      return searchSessionManager.current.activeSessionId 
        ? searchSessionManager.current.getSession(searchSessionManager.current.activeSessionId)
        : null;
    },
    
    // 取消会话
    cancelSession: (sessionId) => {
      const session = searchSessionManager.current.getSession(sessionId);
      if (session) {
        searchSessionManager.current.updateSession(sessionId, { status: 'cancelled' });
        searchSessionManager.current.cleanupSession(sessionId);
      }
    }
  });
  
  // 搜索状态管理
  const [searchState, setSearchState] = useState({
    results: [],
    loading: false,
    hasMore: false,
    pageToken: null,
    totalUniqueSpaces: 0,
    fetchedSpaces: 0,
    activeSessions: new Set(),
    progressInfo: new Map()
  });
  
  // 处理搜索输入变化
  const handleSearchChange = (e) => {
    setSearchKeyword(e.target.value);
  };
  
  // 状态机驱动的搜索执行
  const executeSearchStateMachine = useCallback(async (sessionId) => {
    const session = searchSessionManager.current.getSession(sessionId);
    if (!session) return;
    
    try {
      // 状态机转换
      switch (session.status) {
        case 'initializing':
          // 执行初始搜索
          await performInitialSearch(sessionId);
          break;
          
        case 'processing':
          // 搜索完成
          searchSessionManager.current.updateSession(sessionId, { status: 'completed' });
          break;
          
        case 'completed':
        case 'failed':
        case 'cancelled':
          // 清理资源
          searchSessionManager.current.cleanupSession(sessionId);
          break;
      }
    } catch (error) {
      console.error(`Search session ${sessionId} error:`, error);
      handleSearchError(sessionId, error);
    }
  }, []);
  
  // 执行初始搜索
  const performInitialSearch = async (sessionId) => {
    const session = searchSessionManager.current.getSession(sessionId);
    if (!session) return;
    
    try {
      searchSessionManager.current.updateSession(sessionId, { status: 'processing' });
      updateSearchState({ loading: true });
      
      // 构建搜索参数，第一次搜索不包含page_token
      const params = { query: session.keyword, page_size: 10 };
      // 只有在明确需要分页时才添加page_token参数
      if (session.token && session.token !== 'initial') {
        params.page_token = session.token;
      }
      
      // 获取用户访问令牌
      const userAccessToken = localStorage.getItem('user_access_token');
      if (!userAccessToken) {
        throw new Error('User Access Token not found');
      }
      
      // 使用fetch API处理流式响应，替代EventSource
      const response = await fetch('/api/wiki/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${userAccessToken}`
        },
        body: JSON.stringify(params)
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // 处理完整的事件
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const dataStr = line.slice(6);
              // 检查是否为[DONE]标记
              if (dataStr === '[DONE]') {
                // 流结束
                reader.cancel();
                break;
              }
              
              const data = JSON.parse(dataStr);
              
              switch (data.type) {
                case 'initial':
                  // 更新会话信息
                  searchSessionManager.current.updateSession(sessionId, {
                    hasMore: data.has_more,
                    pageToken: data.page_token,
                    totalUniqueSpaces: data.total_unique_spaces
                  });
                  
                  // 更新UI状态
                  updateSearchState({
                    hasMore: data.has_more,
                    pageToken: data.page_token,
                    totalUniqueSpaces: data.total_unique_spaces,
                    fetchedSpaces: 0
                  });
                  break;
                  
                case 'detail':
                  // 更新会话信息
                  searchSessionManager.current.updateSession(sessionId, {
                    results: [...(session.results || []), data.item],
                    fetchedSpaces: data.fetched_count
                  });
                  
                  // 立即更新UI状态，确保每获取到一条详情就立即显示
                  setSearchState(prevState => ({
                    ...prevState,
                    results: [...prevState.results, data.item],
                    fetchedSpaces: data.fetched_count
                  }));
                  break;
                  
                case 'complete':
                  // 搜索完成
                  searchSessionManager.current.updateSession(sessionId, { status: 'completed' });
                  updateSearchState({ loading: false });
                  break;
                  
                case '[DONE]':
                  // 流结束
                  reader.cancel();
                  break;
              }
            } catch (error) {
              console.error('Error parsing stream data:', error);
            }
          }
        }
      }
      
    } catch (error) {
      console.error('Stream connection failed:', error);
      handleSearchError(sessionId, new Error(`Stream connection failed: ${error.message}`));
    }
  };

  // 统一的错误处理
  const handleSearchError = (sessionId, error) => {
    console.error(`Search error for session ${sessionId}:`, error);
    
    searchSessionManager.current.updateSession(sessionId, { status: 'failed' });
    updateSearchState({ loading: false });
    
    // 根据错误类型显示不同的错误信息
    let errorMessage = '搜索失败，请稍后重试。';
    if (error.response) {
      switch (error.response.status) {
        case 401:
          errorMessage = '认证失败，请重新登录。';
          break;
        case 429:
          errorMessage = '请求过于频繁，请稍后再试。';
          break;
        case 500:
          errorMessage = '服务器内部错误，请稍后重试。';
          break;
        default:
          errorMessage = `搜索失败: ${error.response.data?.error || error.message}`;
      }
    } else if (error.message) {
      errorMessage = `网络错误: ${error.message}`;
    }
    
    message.error(errorMessage);
  };

  // 加载更多搜索结果 - 适配新的会话管理
  const loadMoreSearchResults = () => {
    const activeSession = searchSessionManager.current.getActiveSession();
    if (activeSession && activeSession.hasMore && !searchState.loading) {
      // 使用当前活跃会话的关键词和分页token继续搜索
      performSearch(activeSession.keyword, activeSession.pageToken);
    }
  };

  // 统一的搜索状态更新函数
  const updateSearchState = useCallback((updates) => {
    setSearchState(prev => {
      const newState = { ...prev, ...updates };
      
      // 更新活跃会话集合
      if (updates.activeSessions !== undefined) {
        newState.activeSessions = updates.activeSessions;
      } else {
        // 自动同步活跃会话
        const activeSessionIds = new Set();
        searchSessionManager.current.sessions.forEach((session, id) => {
          if (['initializing', 'processing'].includes(session.status)) {
            activeSessionIds.add(id);
          }
        });
        newState.activeSessions = activeSessionIds;
      }
      
      return newState;
    });
  }, []);
  
  // 执行搜索 - 对外接口
  const performSearch = useCallback((keyword, token = null) => {
    if (!keyword.trim()) {
      updateSearchState({
        results: [],
        hasMore: false,
        pageToken: null,
        progressInfo: new Map()
      });
      return;
    }
    
    // 创建新的搜索会话
    const sessionId = searchSessionManager.current.createSession(keyword, token);
    
    // 启动状态机
    executeSearchStateMachine(sessionId);
    
  }, [executeSearchStateMachine, updateSearchState]);

  // 搜索框回车事件
  const handleSearchPressEnter = () => {
    performSearch(searchKeyword);
    setIsModalOpen(true); // 打开模态框显示搜索结果
  };

  // 关闭搜索结果模态框 - 清理会话资源
  const handleModalClose = () => {
    setIsModalOpen(false);
    
    // 清理所有活跃的搜索会话
    const activeSessionIds = Array.from(searchState.activeSessions);
    activeSessionIds.forEach(sessionId => {
      searchSessionManager.current.cancelSession(sessionId);
    });
    
    // 重置搜索状态
    updateSearchState({
      results: [],
      activeSessions: new Set(),
      progressInfo: new Map()
    });
    
    // 保留搜索关键词，方便用户继续搜索
  };
  
  // 响应式网格配置状态
  const [gridConfig, setGridConfig] = useState({
    gutter: 24,
    xs: 1,
    sm: 2,
    md: 3,
    lg: 4,
    xl: 5,
    xxl: 6
  });

  // 卡片颜色缓存
  const [cardColors, setCardColors] = useState(new Map());
  
  // 动画配置状态
  const [animationConfig, setAnimationConfig] = useState({
    gradientFlow: 'gradientFlow 8s linear infinite',
    isAnimationEnabled: true,
    performanceLevel: 'HIGH'
  });
  
  // 动画管理器引用
  const animationManagerRef = useRef(null);
  
  // 性能监控引用
  const performanceMonitorRef = useRef(null);
  
  // 性能状态
  const [performanceStatus, setPerformanceStatus] = useState({
    level: 'good',
    fps: 60,
    memory: 0,
    isMonitoring: false
  });



  const loadMoreData = useCallback(() => {
    if (loading.current || !hasMore) return;
    loading.current = true;

    const params = { page_size: 20 };
    if (pageToken) {
      params.page_token = pageToken;
    }

    apiClient.get('/api/wiki/spaces', { params })
      .then(response => {
        const { items = [], has_more, page_token } = response.data;
        setSpaces(prevSpaces => [...prevSpaces, ...items]);
        setHasMore(has_more);
        setPageToken(page_token);
      })
      .catch(error => {
        console.error('Error fetching wiki spaces:', error);
        message.error('加载知识空间失败，请稍后重试。');
      })
      .finally(() => {
        loading.current = false;
      });
  }, [pageToken, hasMore]);

  // 组件卸载时清理资源 - 健壮性优化
  useEffect(() => {
    return () => {
      // 清理所有的搜索会话资源
      searchSessionManager.current.sessions.forEach((session, sessionId) => {
        searchSessionManager.current.cleanupSession(sessionId);
      });
      searchSessionManager.current.sessions.clear();
      searchSessionManager.current.activeSessionId = null;
      
      console.log('Wiki component: All search sessions cleaned up');
    };
  }, []);
  
  useEffect(() => {
    if (spaces.length === 0) {
      loadMoreData();
    }
  }, [loadMoreData, spaces.length]);

  // 初始化卡片聚光灯效果
  useEffect(() => {
    // 初始化聚光灯效果
    const spotlightInstance = initCardSpotlight({
      selector: '.wiki-list .ant-card',
      spotlightOpacity: 0.15,
      spotlightSize: 200,
      transitionDuration: 0.3,
      enableOnMobile: false
    });

    // 组件卸载时清理资源
    return () => {
      destroyCardSpotlight();
    };
  }, []);

  // 初始化动画配置管理器
  useEffect(() => {
    // 获取动画管理器实例
    const animationManager = getAnimationManager();
    animationManagerRef.current = animationManager;
    
    // 处理动画配置变化
    const handleAnimationConfigChange = (performanceLevel, performanceConfig) => {
      const gradientFlowAnimation = getGradientFlowAnimation();
      
      setAnimationConfig({
        gradientFlow: gradientFlowAnimation,
        isAnimationEnabled: performanceConfig.enabled,
        performanceLevel: performanceLevel
      });
    };
    
    // 监听动画配置变化
    animationManager.addObserver(handleAnimationConfigChange);
    
    // 组件卸载时清理资源
    return () => {
      animationManager.removeObserver(handleAnimationConfigChange);
    };
  }, []);

  // 初始化性能监控
  useEffect(() => {
    // 获取性能监控实例
    const performanceMonitor = getPerformanceMonitor();
    performanceMonitorRef.current = performanceMonitor;
    
    // 处理性能状态变化
    const handlePerformanceStatusChange = (status) => {
      setPerformanceStatus({
        level: status.level,
        fps: status.fps,
        memory: status.memory,
        isMonitoring: status.isMonitoring
      });
    };
    
    // 启动性能监控
    performanceMonitor.startMonitoring();
    
    // 监听性能状态变化
    performanceMonitor.addObserver(handlePerformanceStatusChange);
    
    // 组件卸载时清理资源
    return () => {
      performanceMonitor.stopMonitoring();
      performanceMonitor.removeObserver(handlePerformanceStatusChange);
    };
  }, []);

  // 获取性能优化建议
  const getPerformanceRecommendations = (report) => {
    const recommendations = [];
    const { summary, details } = report;
    
    // FPS相关建议
    if (details.fps.level === 'critical' || details.fps.level === 'poor') {
      recommendations.push({
        type: 'fps',
        priority: 'high',
        message: 'FPS过低，建议禁用动画效果',
        action: 'disable_animations'
      });
    }
    
    // 内存相关建议
    if (details.memory.level === 'critical' || details.memory.level === 'poor') {
      recommendations.push({
        type: 'memory',
        priority: 'high',
        message: '内存使用过高，建议清理缓存',
        action: 'clear_cache'
      });
    }
    
    // 网络相关建议
    if (details.system.connection && 
        (details.system.connection.effectiveType === '2g' || 
         details.system.connection.saveData)) {
      recommendations.push({
        type: 'network',
        priority: 'medium',
        message: '网络连接较慢，建议启用数据节省模式',
        action: 'enable_data_saver'
      });
    }
    
    // 设备相关建议
    if (details.system.deviceMemory && details.system.deviceMemory < 2) {
      recommendations.push({
        type: 'device',
        priority: 'medium',
        message: '设备内存较低，建议简化界面效果',
        action: 'simplify_ui'
      });
    }
    
    return recommendations;
  };

  // 定期性能报告
  useEffect(() => {
    if (!performanceMonitorRef.current) {
      return;
    }
    
    const reportInterval = setInterval(() => {
      const report = performanceMonitorRef.current.generateReport();
      
      // 更新性能状态
      setPerformanceStatus(prev => ({
        ...prev,
        level: report.summary.level,
        fps: report.details.fps.average,
        memory: report.details.memory.averagePercentage
      }));
      
      // 记录详细报告
      console.log('Performance report:', {
        timestamp: new Date().toISOString(),
        summary: report.summary,
        spacesCount: spaces.length,
        cardColorsCount: cardColors.size,
        animationEnabled: animationConfig.isAnimationEnabled
      });
      
      // 如果性能较差，发出警告
      if (report.summary.level === 'critical' || report.summary.level === 'poor') {
        console.warn('Poor performance detected:', {
          level: report.summary.level,
          fps: report.details.fps,
          memory: report.details.memory,
          recommendations: getPerformanceRecommendations(report)
        });
      }
    }, 30000); // 每30秒生成一次报告
    
    return () => {
      clearInterval(reportInterval);
    };
  }, [spaces.length, cardColors.size, animationConfig.isAnimationEnabled]);

  // 初始化响应式网格
  useEffect(() => {
    // 获取响应式网格实例
    const responsiveGrid = getResponsiveGrid();
    
    // 处理屏幕尺寸变化
    const handleResize = (config) => {
      // 根据屏幕尺寸调整网格配置
      const newGridConfig = responsiveGrid.getListGridConfig({
          containerWidth: window.innerWidth,
          minCardWidth: 320 // 调大卡片最小宽度，从280px增加到320px，适应大屏幕需求
        });
      
      setGridConfig(newGridConfig);
      
      // 记录响应式调整日志
      console.log('Responsive grid updated:', {
        breakpoint: config.breakpoint,
        columns: newGridConfig.lg,
        screenWidth: config.screenWidth,
        timestamp: new Date().toISOString()
      });
    };

    // 初始设置
    const initialConfig = responsiveGrid.getCurrentConfig();
    handleResize(initialConfig);

    // 监听屏幕尺寸变化
    responsiveGrid.observeResize(handleResize);

    // 组件卸载时清理资源
    return () => {
      responsiveGrid.unobserveResize();
    };
  }, []);

  // 统一的Loading组件
  const renderLoading = (tip = "加载中...", size = "default", center = true) => (
    <div style={{ 
      textAlign: center ? 'center' : 'left', 
      padding: center ? '20px 0' : '10px 0',
      width: '100%'
    }}>
      <Spin 
        size={size} 
        tip={tip}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: center ? 'center' : 'flex-start'
        }}
      />
    </div>
  );

  return (
    <div>
      {/* 标题区域 - 直接显示在底色上 */}
      <div className="wiki-title-section">
        <div className="wiki-title-container">
          <div className="wiki-title-content">
            <h1 className="wiki-title">AI 知识官</h1>
            <div className="wiki-subtitle">——"企业知识管理的精密校准仪，让大模型助力每一个企业构建夯实知识架构"</div>
          </div>
          <div className="wiki-title-actions">
            <Button onClick={() => navigate('/config')}>
              <span>AI 分析配置</span>
            </Button>
          </div>
        </div>
      </div>
      {/* 搜索框区域 */}
      <div className="wiki-search-section">
        <div className="wiki-search-container">
          <Input
            placeholder="搜索知识库..."
            prefix={<SearchOutlined />}
            value={searchKeyword}
            onChange={handleSearchChange}
            onPressEnter={handleSearchPressEnter}
            allowClear
          />
        </div>
      </div>
      <main className="wiki-content">
        <InfiniteScroll
          dataLength={spaces.length}
          next={loadMoreData}
          hasMore={hasMore}
          loader={renderLoading("加载中...", "default", true)}
          endMessage={<div style={{ textAlign: 'center', padding: '20px 0' }}><b>没有更多了</b></div>}
        >
          <List
            className="wiki-list"
            grid={gridConfig}
            dataSource={spaces}
            renderItem={item => {
              // 获取或生成卡片颜色
              let cardColor = cardColors.get(item.space_id);
              if (!cardColor) {
                cardColor = generateCardColor(item.space_id);
                // 使用useEffect来更新卡片颜色，避免在渲染过程中直接更新状态
                setTimeout(() => {
                  setCardColors(prevColors => {
                    const newCardColors = new Map(prevColors);
                    newCardColors.set(item.space_id, cardColor);
                    return newCardColors;
                  });
                }, 0);
              }
              
              return (
                <List.Item key={item.space_id}>
                  <Link to={`/wiki/${item.space_id}`} style={{ display: 'block' }}>
                    <Card 
                      hoverable 
                      className="wiki-card-vertical"
                      style={{
                        background: `linear-gradient(315deg, ${cardColor?.primaryColor || '#ffffff'}, ${cardColor?.secondaryColor || '#f0f0f0'})`,
                        position: 'relative',
                        overflow: 'hidden'
                      }}
                      cover={
                        <div 
                          className="wiki-card-cover" 
                          style={{
                            position: 'relative',
                            overflow: 'hidden'
                          }}
                        >
                        </div>
                      }
                    >
                      {/* 哑光效果叠加层 - 移动到卡片级别 */}
                      <div 
                        className="wiki-card-matte-overlay"
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          right: 0,
                          bottom: 0,
                          background: cardColor?.overlay || 'rgba(255, 255, 255, 0.3)',
                          pointerEvents: 'none'
                        }}
                      />
                      <Card.Meta 
                        title={<div className="wiki-card-title">{item.name || item.title || '未命名空间'}</div>} 
                        description={<div className="wiki-card-description">{item.description || '暂无描述'}</div>}
                      />
                    </Card>
                  </Link>
                </List.Item>
              );
            }}
          />
        </InfiniteScroll>
      </main>

      {/* 搜索结果模态框 */}
      <Modal
        title="搜索结果"
        open={isModalOpen}
        onCancel={handleModalClose}
        footer={null}
        width={800}
        className="wiki-search-modal"
      >
        {/* 显示搜索进度信息 */}
        {searchState.totalUniqueSpaces > 0 && (
          <div style={{ 
            marginBottom: '16px', 
            padding: '12px', 
            backgroundColor: '#f0f8ff', 
            borderRadius: '8px',
            border: '1px solid #d0e8ff',
            color: '#333',
            fontSize: '14px'
          }}>
            {searchState.loading ? (
              `已找到 ${searchState.fetchedSpaces} 个知识库，正在持续寻找`
            ) : (
              `已完成知识库检索，共找到 ${searchState.fetchedSpaces} 个`
            )}
          </div>
        )}
        
        <div className="wiki-search-results-container" id="scrollableSearchDiv">
          <InfiniteScroll
            dataLength={searchState.results.length}
            next={loadMoreSearchResults}
            hasMore={searchState.hasMore}
            loader={searchState.loading && renderLoading("加载更多...", "small", true)}
            scrollableTarget="scrollableSearchDiv"
          >
            {searchState.loading && searchState.results.length === 0 ? (
              renderLoading("正在努力搜索中...", "large", true)
            ) : searchState.results.length > 0 ? (
              <List
                itemLayout="vertical"
                dataSource={searchState.results}
                renderItem={item => (
                  <List.Item key={item.space_id}>
                    <Card
                      hoverable
                      className="wiki-search-result-card"
                      onClick={() => {
                        // 直接跳转到知识库详情页
                        navigate(`/wiki/${item.space_id}`);
                        handleModalClose();
                      }}
                    >
                      <div className="wiki-search-result-content">
                        <div className="wiki-search-result-meta">
                          <Space wrap>
                            {item.icon && (
                              <span className="wiki-search-result-icon">{item.icon}</span>
                            )}
                            <span className="wiki-search-result-space">知识空间</span>
                            {item.is_starred && <Tag color="gold">已收藏</Tag>}
                          </Space>
                        </div>
                        <h3 className="wiki-search-result-title">{item.title}</h3>
                        <p className="wiki-search-result-summary">{item.description || '暂无描述'}</p>
                        {(item.updated_time && item.updated_time > 0) || (item.created_time && item.created_time > 0 && item.created_time !== item.updated_time) ? (
                          <div className="wiki-search-result-time">
                            {item.updated_time && item.updated_time > 0 && (
                              <span>更新于: {new Date(item.updated_time * 1000).toLocaleDateString()}</span>
                            )}
                            {item.created_time && item.created_time > 0 && item.created_time !== item.updated_time && (
                              <span>创建于: {new Date(item.created_time * 1000).toLocaleDateString()}</span>
                            )}
                          </div>
                        ) : null}
                      </div>
                    </Card>
                  </List.Item>
                )}
              />
            ) : (
              !searchState.loading && <Empty description="没有找到相关结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </InfiniteScroll>
        </div>
      </Modal>
    </div>
  );
}

export default Wiki;