use regex::Regex;
use clap::Parser;
use std::io::{self, Read};

#[derive(Parser)]
#[command(name = "efke-chunk", about = "Fast text chunking for RAG")]
struct Args {
    #[arg(short, long, default_value = "900")]
    size: usize,
    
    #[arg(short, long, default_value = "120")]
    overlap: usize,
    
    #[arg(short, long)]
    file: Option<String>,
}

fn split_chunks(text: &str, size: usize, overlap: usize) -> Vec<(usize, usize, String)> {
    let clean: String = text.split_whitespace().collect::<Vec<&str>>().join(" ");
    let chars: Vec<char> = clean.chars().collect();
    let mut chunks = Vec::new();
    let mut start = 0;
    while start < chars.len() {
        let end = std::cmp::min(chars.len(), start + size);
        let chunk: String = chars[start..end].iter().collect();
        chunks.push((start, end, chunk));
        if end == chars.len() { break; }
        start = if end > overlap { end - overlap } else { 0 };
    }
    chunks
}

fn clean_text(text: &str) -> String {
    let noise = Regex::new(r"(作者|出版社|地址|電話|傳真|mail|版權|頁碼|詳見圖|如下圖所示|點擊訂購|免費辦理|客服微信|\d{2,4}[-‐]?\d{6,8}|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})").unwrap();
    let cleaned = noise.replace_all(text, "");
    let lines: Vec<&str> = cleaned.lines()
        .filter(|l| l.trim().len() > 10)
        .collect();
    lines.join("\n")
}

fn main() {
    let args = Args::parse();
    let mut input = String::new();
    if let Some(ref file) = args.file {
        input = std::fs::read_to_string(file).expect("Cannot read file");
    } else {
        io::stdin().read_to_string(&mut input).expect("Cannot read stdin");
    }
    
    let cleaned = clean_text(&input);
    let chunks = split_chunks(&cleaned, args.size, args.overlap);
    
    for (i, (start, end, chunk)) in chunks.iter().enumerate() {
        println!("{{\"index\":{},\"start\":{},\"end\":{},\"content\":\"{}\"}}",
            i, start, end, chunk.replace('\\', "\\\\").replace('"', "\\\"").replace('\n', "\\n"));
    }
}
