use sha2::{Sha256, Digest};
use std::fs;
use std::io::Read;
use clap::Parser;

#[derive(Parser)]
#[command(name = "efke-hash", about = "Fast SHA256 file hashing")]
struct Args {
    #[arg(short, long)]
    file: String,
    
    #[arg(short, long, default_value = "hex")]
    format: String,
}

fn hash_file(path: &str) -> Result<String, Box<dyn std::error::Error>> {
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

fn main() {
    let args = Args::parse();
    match hash_file(&args.file) {
        Ok(hash) => {
            if args.format == "hex" {
                println!("{}", hash);
            } else {
                println!("{{\"file\":\"{}\",\"sha256\":\"{}\"}}", args.file, hash);
            }
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            std::process::exit(1);
        }
    }
}
