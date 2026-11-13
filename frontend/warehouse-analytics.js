const host = document.getElementById('warehouse-analytics-chart');
if (host) {
  try {
    const {default: Vizzu} = await import('https://cdn.jsdelivr.net/npm/vizzu@0.18/dist/vizzu.min.js');
    const chart = new Vizzu('warehouse-analytics-chart');
    let ready = false;
    let pending = null;
    let renderFlight = null;
    const render = stats => {
      pending = stats;
      if (renderFlight) return renderFlight;
      renderFlight = (async () => {
        while (pending) {
          const nextStats = pending;
          pending = null;
          await renderNow(nextStats);
        }
      })().finally(() => { renderFlight = null; });
      return renderFlight;
    };
    const renderNow = async (stats) => {
      const values = [
        ['Thẻ hoạt động', Number(stats.active_cards) || 0],
        ['Lượt quẹt hôm nay', Number(stats.scans_today) || 0],
        ['Từ chối hôm nay', Number(stats.denied_today) || 0],
        ['Cảnh báo hôm nay', Number(stats.alerts_today) || 0]
      ];
      const state = {
        data: {series:[
          {name:'Metric', type:'dimension', values:values.map(x=>x[0])},
          {name:'Count', type:'measure', values:values.map(x=>x[1])}
        ]},
        config: {
          title: 'THỐNG KÊ VẬN HÀNH',
          channels: {x:{set:['Metric']}, y:{set:['Count']}, color:{set:['Metric']}},
          geometry: 'rectangle'
        },
        style: {
          backgroundColor:'#0b1b29', fontFamily:'DM Sans, sans-serif', fontSize:'12px',
          title:{color:'#d7eaf2',fontFamily:'Space Grotesk, sans-serif',fontSize:'16px'},
          xAxis:{color:'#9bb2c0',label:{color:'#9bb2c0'}},
          yAxis:{color:'#7894a7',label:{color:'#9bb2c0'},guides:{color:'#284354'}},
          legend:{label:{color:'#a9c0cc'}},
          plot:{backgroundColor:'#0b1b29',marker:{colorPalette:'#36c9d5 #4c9fd8 #e5a94e #e36b7a'}}
        }
      };
      if (!ready) {
        await chart.initializing;
        await chart.animate(state);
        ready = true;
      } else {
        await chart.animate(state, {duration:0.7});
      }
      const stamp=document.getElementById('analytics-updated');
      if(stamp) stamp.textContent=`CẬP NHẬT ${new Date().toLocaleTimeString('vi-VN')}`;
    };
    window.KhoAIAnalytics={update(stats){render(stats).catch(err=>console.warn('Vizzu update failed:',err));}};
    const initialStats = window.__khoaiPendingAnalyticsStats;
    if (initialStats) {
      delete window.__khoaiPendingAnalyticsStats;
      render(initialStats).catch(err=>console.warn('Vizzu update failed:',err));
    }
  } catch (error) {
    console.warn('KhoAI analytics unavailable:', error);
    host.classList.add('analytics-fallback');
    host.innerHTML='<p>Biểu đồ thanh dự phòng · Không cần tải thư viện bên ngoài.</p><div class="analytics-fallback-bars" aria-label="Biểu đồ thống kê dự phòng"></div>';
    window.KhoAIAnalytics={update(stats={}){
      const values=[['Thẻ hoạt động',Number(stats.active_cards)||0],['Lượt quẹt hôm nay',Number(stats.scans_today)||0],['Từ chối hôm nay',Number(stats.denied_today)||0],['Cảnh báo hôm nay',Number(stats.alerts_today)||0]];
      const max=Math.max(1,...values.map(v=>v[1]));const bars=host.querySelector('.analytics-fallback-bars');
      if(bars)bars.innerHTML=values.map(([label,value])=>`<div class="fallback-bar-row"><span>${label}</span><div><i style="width:${Math.max(1,value/max*100)}%"></i></div><b>${value}</b></div>`).join('');
      const stamp=document.getElementById('analytics-updated');if(stamp)stamp.textContent=`CẬP NHẬT ${new Date().toLocaleTimeString('vi-VN')} · CHẾ ĐỘ DỰ PHÒNG`;
    }};
    const initialStats = window.__khoaiPendingAnalyticsStats || {};
    delete window.__khoaiPendingAnalyticsStats;
    window.KhoAIAnalytics.update(initialStats);
  }
}
