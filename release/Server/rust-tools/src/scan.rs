use walkdir::WalkDir;
use rayon::prelude::*;
use sha2::{Sha256, Digest};
use std::fs;
use std::io::Read;
use clap::Parser;

#[derive(Parser)]
#[command(name = "efke-scan", about = "Fast parallel file scanning with hashing")]
struct Args {
    #[arg(short, long)]
    directory: String,
    
    #[arg(short, long, default_value = "json")]
    format: String,
    
    #[arg(short, long, default_value = "pdf,txt,jpg,jpeg,png,epub")]
    extensions: String,
}

fn hash_file(path: &std::path::Path) -> Result<String, Box<dyn std::error::Error>> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let bytes_read = file.read(&mut buffer)?;
        if bytes_read == 0 { break; }
        hasher.update(&buffer[..bytes_read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

#[derive(serde::Serialize)]
struct FileInfo {
    path: String,
    size: u64,
    sha256: String,
}

fn main() {
    let args = Args::parse();
    let exts: Vec<String> = args.extensions.split(',').map(|s| s.trim().to_lowercase()).collect();
    
    let files: Vec<_> = WalkDir::new(&args.directory)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
        .filter(|e| {
            exts.iter().any(|ext| {
                e.path().extension()
                    .and_then(|s| s.to_str())
                    .map(|s| s.eq_ignore_ascii_case(ext))
                    .unwrap_or(false)
            })
        })
        .collect();
    
    let total = files.len();
    let results: Vec<FileInfo> = files.par_iter()
        .filter_map(|entry| {
            let path = entry.path();
            let metadata = fs::metadata(path).ok()?;
            let sha = hash_file(path).ok()?;
            Some(FileInfo {
                path: path.display().to_string(),
                size: metadata.len(),
                sha256: sha,
            })
        })
        .collect();
    
    if args.format == "json" {
        println!("{}", serde_json::to_string(&results).unwrap());
    } else {
        println!("Total files: {}", total);
        for r in &results {
            println!("{}\t{}\t{}", r.path, r.size, r.sha256);
        }
    }
}
