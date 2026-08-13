use axum::{
    extract::{
        ws::{WebSocket, WebSocketUpgrade, Message},
        State,
    },
    response::Html,
    routing::get, Router,
};
use futures_util::{SinkExt, StreamExt};
use reqwest::Client;
use serde_json::Value;
use tokio::sync::broadcast;
use tower_http::cors::CorsLayer;

const MC: &str = "http://127.0.0.1:8420";
const POLL_MS: u64 = 1000;

type Tx = broadcast::Sender<String>;

async fn index() -> Html<&'static str> {
    Html(r#"<!DOCTYPE html>
<html>
<head>
<title>Realtime Stream</title>
<style>
body{background:#05070a;color:#c8d2dc;font:13px ui-monospace,Consolas,monospace;margin:0;padding:10px}
#feed{white-space:pre-wrap;word-break:break-all}
.ts{color:#6b7785}
.src-copier{color:#ffb000}
.src-shadow{color:#ff10f0}
.src-xvenue{color:#06b6d4}
.src-polynews{color:#39ff14}
.src-news{color:#ffb020}
</style>
</head>
<body>
<h3>Realtime Stream</h3>
<div id="feed">connecting...</div>
<script>
const feed=document.getElementById('feed');
const ws=new WebSocket(`ws://${location.host}/ws`);
ws.onmessage=(e)=>{
  const line=document.createElement('div');
  line.innerHTML=e.data;
  feed.appendChild(line);
  while(feed.children.length>200)feed.removeChild(feed.firstChild);
  feed.scrollTop=feed.scrollHeight;
};
ws.onclose=()=>{feed.innerHTML+='<div class="ts">closed</div>'};
</script>
</body>
</html>"#)
}

async fn ws_handler(ws: WebSocketUpgrade, State(tx): State<Tx>) -> impl axum::response::IntoResponse {
    ws.on_upgrade(|socket| handle_socket(socket, tx))
}

async fn handle_socket(socket: WebSocket, tx: Tx) {
    let (mut tx_ws, mut rx_ws) = socket.split();
    let mut rx_bcast = tx.subscribe();

    let send = async move {
        while let Ok(msg) = rx_bcast.recv().await {
            if tx_ws.send(Message::Text(msg.into())).await.is_err() {
                break;
            }
        }
    };
    let recv = async move {
        while let Some(Ok(_)) = rx_ws.next().await {}
    };

    tokio::join!(send, recv);
}

async fn poll_mc(tx: Tx) {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .build()
        .unwrap();

    let mut seen = std::collections::HashSet::new();

    loop {
        tokio::time::sleep(std::time::Duration::from_millis(POLL_MS)).await;

        match client.get(format!("{}/api/trade/events", MC)).send().await {
            Ok(resp) if resp.status().is_success() => {
                if let Ok(data) = resp.json::<Value>().await {
                    if let Some(events) = data.get("events").and_then(|e| e.as_array()) {
                        for ev in events.iter().take(20) {
                            let key = format!("{}:{}",
                                ev.get("source").and_then(|s| s.as_str()).unwrap_or("?"),
                                ev.get("ts").and_then(|t| t.as_str()).unwrap_or("?")
                            );
                            if seen.insert(key) {
                                let ts = ev.get("ts").and_then(|t| t.as_str()).unwrap_or("--");
                                let src = ev.get("source").and_then(|s| s.as_str()).unwrap_or("?");
                                let detail = ev.get("detail").and_then(|d| d.as_str()).unwrap_or("");
                                let line = format!(r#"<span class="ts">[{}]</span> <span class="src-{}">{}</span> {}"#,
                                    ts, src, src.to_uppercase(), detail);
                                let _ = tx.send(line);
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }
}

#[tokio::main]
async fn main() {
    let (tx, _) = broadcast::channel::<String>(1000);

    let app = Router::new()
        .route("/", get(index))
        .route("/ws", get(ws_handler))
        .layer(CorsLayer::permissive())
        .with_state(tx.clone());

    let addr: std::net::SocketAddr = "127.0.0.1:4242".parse().unwrap();
    println!("stream view on http://127.0.0.1:4242");

    let server = axum::serve(
        tokio::net::TcpListener::bind(addr).await.unwrap(),
        app.into_make_service(),
    );
    tokio::spawn(async move {
        poll_mc(tx).await;
    });

    server.await.unwrap();
}
