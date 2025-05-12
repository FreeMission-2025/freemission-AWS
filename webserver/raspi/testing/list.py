import os
import sys


import av

def list_available_decoders():
    print("Available video decoders:")
    for name in av.codec.codecs_available:
        try:
            codec = av.Codec(name, 'r')  # 'r' for reading (decoder)
            if codec.type == 'video':
                print(f"  {name}: {codec.long_name}")
        except:
            continue  # Skip if not a decoder or invalid

    print("\nAvailable audio decoders:")
    for name in av.codec.codecs_available:
        try:
            codec = av.Codec(name, 'r')
            if codec.type == 'audio':
                print(f"  {name}: {codec.long_name}")
        except:
            continue

def list_available_encoders():
    print("Available video encoders:")
    for name in av.codec.codecs_available:
        try:
            codec = av.Codec(name, 'w')  # 'w' for writing (encoder)
            print(f"  {name}: {codec.long_name}")
        except:
            continue  # Skip if not an encoder or invalid

if __name__ == "__main__":
    list_available_encoders()


''' 
import av

print("Available video decoders:\n")

for name in av.codecs_available:
    try:
        codec = av.codec.Codec(name, 'r')  # 'r' for decoder
        if codec.type == 'video':
            print(f"- {codec.name} ({codec.long_name})")
    except Exception:
        continue  # Ignore codecs that can't be opened as decoders

'''
'''
(venv) ubuntu@ip-172-31-25-68:~/aws$ python list.py
Available video encoders:
  h263: H.263 / H.263-1996
  libopencore_amrnb: OpenCORE AMR-NB (Adaptive Multi-Rate Narrow-Band)
  pcm_f64le: PCM 64-bit floating point little-endian
  tiff: TIFF image
  adpcm_ima_alp: ADPCM IMA High Voltage Software ALP
  prores_ks: Apple ProRes (iCodec Pro)
  pcm_s32le_planar: PCM signed 32-bit little-endian planar
  pcm_f32le: PCM 32-bit floating point little-endian
  av1_nvenc: NVIDIA NVENC av1 encoder
  bitpacked: Bitpacked
  r210: Uncompressed RGB 10-bit
  targa: Truevision Targa image
  yuv4: Uncompressed packed 4:2:0
  text: Raw text subtitle
  tta: TTA (True Audio)
  mp2fixed: MP2 fixed point (MPEG audio layer 2)
  adpcm_ms: ADPCM Microsoft
  libsvtav1: SVT-AV1(Scalable Video Technology for AV1) encoder
  jpeg2000: JPEG 2000
  msvideo1: Microsoft Video-1
  adpcm_yamaha: ADPCM Yamaha
  y41p: Uncompressed YUV 4:1:1 12-bit
  pgmyuv: PGMYUV (Portable GrayMap YUV) image
  pcm_u24be: PCM unsigned 24-bit big-endian
  dpx: DPX (Digital Picture Exchange) image
  rv20: RealVideo 2.0
  mjpeg: MJPEG (Motion JPEG)
  gif: GIF (Graphics Interchange Format)
  prores_aw: Apple ProRes
  libopus: libopus Opus
  bmp: BMP (Windows and OS/2 bitmap)
  a64multi: Multicolor charset for Commodore 64
  pcm_s32be: PCM signed 32-bit big-endian
  avrp: Avid 1:1 10-bit RGB Packer
  zlib: LCL (LossLess Codec Library) ZLIB
  qtrle: QuickTime Animation (RLE) video
  libvorbis: libvorbis
  roqvideo: id RoQ video
  pcm_u32le: PCM unsigned 32-bit little-endian
  pcm_dvd: PCM signed 16|20|24-bit big-endian for DVD media
  libwebp: libwebp WebP image
  msmpeg4: MPEG-4 part 2 Microsoft variant version 3
  pcm_bluray: PCM signed 16|20|24-bit big-endian for Blu-ray media
  qoi: QOI (Quite OK Image format) image
  sbc: SBC (low-complexity subband codec)
  h264_nvenc: NVIDIA NVENC H.264 encoder
  exr: OpenEXR image
  hevc_nvenc: NVIDIA NVENC hevc encoder
  huffyuv: Huffyuv / HuffYUV
  sgi: SGI image
  pcm_mulaw: PCM mu-law / G.711 mu-law
  flac: FLAC (Free Lossless Audio Codec)
  pcm_s8_planar: PCM signed 8-bit planar
  vorbis: libvorbis
  ffvhuff: Huffyuv FFmpeg variant
  adpcm_ima_amv: ADPCM IMA AMV
  r10k: AJA Kona 10-bit RGB Codec
  opus: libopus Opus
  ass: ASS (Advanced SubStation Alpha) subtitle
  ttml: TTML subtitle
  libaom-av1: libaom AV1
  pbm: PBM (Portable BitMap) image
  pcm_s16be: PCM signed 16-bit big-endian
  dnxhd: VC3/DNxHD
  speex: libspeex Speex
  v408: Uncompressed packed QT 4:4:4:4
  adpcm_adx: SEGA CRI ADX ADPCM
  libtwolame: libtwolame MP2 (MPEG audio layer 2)
  h261: H.261
  wmv2: Windows Media Video 8
  g726le: G.726 little endian ADPCM ("right-justified")
  pcm_s64le: PCM signed 64-bit little-endian
  pcm_s16le_planar: PCM signed 16-bit little-endian planar
  pcm_s64be: PCM signed 64-bit big-endian
  subrip: SubRip subtitle
  amv: AMV Video
  ac3_fixed: ATSC A/52A (AC-3)
  pcm_s8: PCM signed 8-bit
  msrle: Microsoft RLE
  libvpx-vp9: libvpx VP9
  sunrast: Sun Rasterfile image
  cinepak: Cinepak
  dirac: SMPTE VC-2
  real_144: RealAudio 1.0 (14.4K)
  pcm_u32be: PCM unsigned 32-bit big-endian
  png: PNG (Portable Network Graphics) image
  utvideo: Ut Video
  vp8: libvpx VP8
  mov_text: 3GPP Timed Text subtitle
  ffv1: FFmpeg video codec #1
  pcm_vidc: PCM Archimedes VIDC
  roq_dpcm: id RoQ DPCM
  mpeg2video: MPEG-2 video
  hdr: HDR (Radiance RGBE format) image
  aptx_hd: aptX HD (Audio Processing Technology for Bluetooth)
  msmpeg4v2: MPEG-4 part 2 Microsoft variant version 2
  g726: G.726 ADPCM
  aac: AAC (Advanced Audio Coding)
  h264: libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
  pcm_s32le: PCM signed 32-bit little-endian
  smc: QuickTime Graphics (SMC)
  flashsv2: Flash Screen Video Version 2
  pcm_s24daud: PCM D-Cinema audio signed 24-bit
  zmbv: Zip Motion Blocks Video
  mp3: libmp3lame MP3 (MPEG audio layer 3)
  adpcm_ima_ssi: ADPCM IMA Simon & Schuster Interactive
  pcm_s16le: PCM signed 16-bit little-endian
  vp9: libvpx VP9
  ljpeg: Lossless JPEG
  pcm_f32be: PCM 32-bit floating point big-endian
  pcm_s24le_planar: PCM signed 24-bit little-endian planar
  dvbsub: DVB subtitles
  aptx: aptX (Audio Processing Technology for Bluetooth)
  a64multi5: Multicolor charset for Commodore 64, extended with 5th color (colram)
  pcm_u16be: PCM unsigned 16-bit big-endian
  pgm: PGM (Portable GrayMap) image
  speedhq: NewTek SpeedHQ
  dxv: Resolume DXV
  pcm_alaw: PCM A-law / G.711 A-law
  g722: G.722 ADPCM
  v410: Uncompressed 4:4:4 10-bit
  pcm_u16le: PCM unsigned 16-bit little-endian
  alias_pix: Alias/Wavefront PIX image
  pcm_s24be: PCM signed 24-bit big-endian
  dfpwm: DFPWM1a audio
  adpcm_ima_apm: ADPCM IMA Ubisoft APM
  prores: Apple ProRes
  h263p: H.263+ / H.263-1998 / H.263 version 2
  ac3: ATSC A/52A (AC-3)
  libspeex: libspeex Speex
  libvpx: libvpx VP8
  libx264: libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
  snow: Snow
  pam: PAM (Portable AnyMap) image
  webp: libwebp WebP image
  wmav1: Windows Media Audio 1
  jpegls: JPEG-LS
  dvvideo: DV (Digital Video)
  xbm: XBM (X BitMap) image
  xface: X-face image
  rpza: QuickTime video (RPZA)
  cfhd: GoPro CineForm HD
  vnull: null video
  v308: Uncompressed packed 4:4:4
  pcm_u8: PCM unsigned 8-bit
  adpcm_ima_ws: ADPCM IMA Westwood
  ssa: ASS (Advanced SubStation Alpha) subtitle
  pfm: PFM (Portable FloatMap) image
  libx264rgb: libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 RGB
  wmv1: Windows Media Video 7
  asv1: ASUS V1
  eac3: ATSC A/52 E-AC-3
  wmav2: Windows Media Audio 2
  asv2: ASUS V2
  flashsv: Flash Screen Video
  libwebp_anim: libwebp WebP image
  pcm_s24le: PCM signed 24-bit little-endian
  wbmp: WBMP (Wireless Application Protocol Bitmap) image
  srt: SubRip subtitle
  xsub: DivX subtitles (XSUB)
  av1: libaom AV1
  pcm_s16be_planar: PCM signed 16-bit big-endian planar
  adpcm_argo: ADPCM Argonaut Games
  ppm: PPM (Portable PixelMap) image
  vbn: Vizrt Binary Image
  vc2: SMPTE VC-2
  fits: Flexible Image Transport System
  hevc: NVIDIA NVENC hevc encoder
  dvdsub: DVD subtitles
  cljr: Cirrus Logic AccuPak
  webvtt: WebVTT subtitle
  wavpack: WavPack
  magicyuv: MagicYUV video
  anull: null audio
  adpcm_ima_wav: ADPCM IMA WAV
  rawvideo: raw video
  rv10: RealVideo 1.0
  mp2: MP2 (MPEG audio layer 2)
  v210: Uncompressed 4:2:2 10-bit
  alac: ALAC (Apple Lossless Audio Codec)
  pcx: PC Paintbrush PCX image
  adpcm_ima_qt: ADPCM IMA QuickTime
  pcm_u24le: PCM unsigned 24-bit little-endian
  xwd: XWD (X Window Dump) image
  wrapped_avframe: AVFrame to AVPacket passthrough
  phm: PHM (Portable HalfFloatMap) image
  flv: FLV / Sorenson Spark / Sorenson H.263 (Flash Video)
  pcm_f64be: PCM 64-bit floating point big-endian
  comfortnoise: RFC 3389 comfort noise generator
  libmp3lame: libmp3lame MP3 (MPEG audio layer 3)
  mpeg4: MPEG-4 part 2
  adpcm_swf: ADPCM Shockwave Flash
  mpeg1video: MPEG-1 video
  nellymoser: Nellymoser Asao
  g723_1: G.723.1
  svq1: Sorenson Vector Quantizer 1 / Sorenson Video 1 / SVQ1
  apng: APNG (Animated Portable Network Graphics) image



Available video decoders:
  cyuv: Creative YUV (CYUV)
  media100: Media 100
  rtv1: RTV1 (RivaTuner Video)
  h261: H.261
  apng: APNG (Animated Portable Network Graphics) image
  dfa: Chronomaster DFA
  brender_pix: BRender PIX image
  rv20: RealVideo 2.0
  dvvideo: DV (Digital Video)
  pcx: PC Paintbrush PCX image
  kmvc: Karl Morton's video codec
  loco: LOCO
  eamad: Electronic Arts Madcow Video
  wbmp: WBMP (Wireless Application Protocol Bitmap) image
  wmv3image: Windows Media Video 9 Image
  msmpeg4: MPEG-4 part 2 Microsoft variant version 3
  pbm: PBM (Portable BitMap) image
  truemotion1: Duck TrueMotion 1.0
  vp9_cuvid: Nvidia CUVID VP9 decoder
  vc1image: Windows Media Video 9 Image v2
  thp: Nintendo Gamecube THP video
  rv10: RealVideo 1.0
  hevc: HEVC (High Efficiency Video Coding)
  xl: Miro VideoXL
  smvjpeg: SMV JPEG
  sheervideo: BitJazz SheerVideo
  rawvideo: raw video
  vmdvideo: Sierra VMD video
  mpeg1_cuvid: Nvidia CUVID MPEG1VIDEO decoder
  magicyuv: MagicYUV video
  flashsv: Flash Screen Video v1
  bitpacked: Bitpacked
  xbm: XBM (X BitMap) image
  truemotion2: Duck TrueMotion 2.0
  c93: Interplay C93
  sgirle: Silicon Graphics RLE 8-bit video
  mvdv: MidiVid VQ
  photocd: Kodak Photo CD
  sanm: LucasArts SANM/Smush video
  m101: Matrox Uncompressed SD
  vp6: On2 VP6
  aura: Auravision AURA
  wcmv: WinCAM Motion Video
  fraps: Fraps
  asv2: ASUS V2
  cpia: CPiA video format
  ffv1: FFmpeg video codec #1
  qtrle: QuickTime Animation (RLE) video
  truemotion2rt: Duck TrueMotion 2.0 Real Time
  mts2: MS Expression Encoder Screen
  vnull: null video
  v210x: Uncompressed 4:2:2 10-bit
  hq_hqa: Canopus HQ/HQA
  jv: Bitmap Brothers JV video
  camstudio: CamStudio
  mpegvideo: MPEG-1 video
  pfm: PFM (Portable FloatMap) image
  amv: AMV Video
  mss2: MS Windows Media Video V9 Screen
  libaom-av1: libaom AV1
  vcr1: ATI VCR1
  vp5: On2 VP5
  svq1: Sorenson Vector Quantizer 1 / Sorenson Video 1 / SVQ1
  cljr: Cirrus Logic AccuPak
  msmpeg4v1: MPEG-4 part 2 Microsoft variant version 1
  nuv: NuppelVideo/RTJPEG
  msa1: MS ATC Screen
  ptx: V.Flash PTX image
  simbiosis_imx: Simbiosis Interactive IMX Video
  vb: Beam Software VB
  mjpeg_cuvid: Nvidia CUVID MJPEG decoder
  vbn: Vizrt Binary Image
  cinepak: Cinepak
  hap: Vidvox Hap
  bethsoftvid: Bethesda VID video
  srgc: Screen Recorder Gold Codec
  cdtoons: CDToons video
  mscc: Mandsoft Screen Capture Codec
  speedhq: NewTek SpeedHQ
  escape124: Escape 124
  smc: QuickTime Graphics (SMC)
  h263: H.263 / H.263-1996, H.263+ / H.263-1998 / H.263 version 2
  dxa: Feeble Files/ScummVM DXA
  jpegls: JPEG-LS
  hnm4video: HNM 4 video
  sp5x: Sunplus JPEG (SP5X)
  rv30: RealVideo 3.0
  mpeg1video: MPEG-1 video
  flic: Autodesk Animator Flic video
  tdsc: TDSC
  camtasia: TechSmith Screen Capture Codec
  cllc: Canopus Lossless Codec
  avs: AVS (Audio Video Standard) video
  wmv1: Windows Media Video 7
  sunrast: Sun Rasterfile image
  v410: Uncompressed 4:4:4 10-bit
  lscr: LEAD Screen Capture
  ppm: PPM (Portable PixelMap) image
  pam: PAM (Portable AnyMap) image
  cdgraphics: CD Graphics video
  indeo4: Intel Indeo Video Interactive 4
  eatgv: Electronic Arts TGV video
  zerocodec: ZeroCodec Lossless Video
  targa: Truevision Targa image
  tscc2: TechSmith Screen Codec 2
  indeo2: Intel Indeo 2
  mwsc: MatchWare Screen Capture Codec
  4xm: 4X Movie
  vp3: On2 VP3
  vp7: On2 VP7
  arbc: Gryphon's Anim Compressor
  cfhd: GoPro CineForm HD
  prosumer: Brooktree ProSumer Video
  xbin: eXtended BINary text
  agm: Amuse Graphics Movie
  avui: Avid Meridien Uncompressed
  indeo5: Intel Indeo Video Interactive 5
  tmv: 8088flex TMV
  mvc2: Silicon Graphics Motion Video Compressor 2
  ultimotion: IBM UltiMotion
  eatgq: Electronic Arts TGQ video
  bintext: Binary text
  iff: IFF ACBM/ANIM/DEEP/ILBM/PBM/RGB8/RGBN
  sgi: SGI image
  xwd: XWD (X Window Dump) image
  gem: GEM Raster image
  libvpx: libvpx VP8
  argo: Argonaut Games Video
  mxpeg: Mobotix MxPEG video
  hevc_cuvid: Nvidia CUVID HEVC decoder
  mvha: MidiVid Archive Codec
  qoi: QOI (Quite OK Image format) image
  ansi: ASCII/ANSI art
  v308: Uncompressed packed 4:4:4
  zlib: LCL (LossLess Codec Library) ZLIB
  screenpresso: Screenpresso
  paf_video: Amazing Studio Packed Animation File Video
  targa_y216: Pinnacle TARGA CineWave YUV16
  h264: H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
  r10k: AJA Kona 10-bit RGB Codec
  svq3: Sorenson Vector Quantizer 3 / Sorenson Video 3 / SVQ3
  vble: VBLE Lossless Codec
  interplayvideo: Interplay MVE video
  vp8: On2 VP8
  vqavideo: Westwood Studios VQA (Vector Quantized Animation) video
  avrp: Avid 1:1 10-bit RGB Packer
  xface: X-face image
  asv1: ASUS V1
  y41p: Uncompressed YUV 4:1:1 12-bit
  xan_wc3: Wing Commander III / Xan
  dxtory: Dxtory
  vp9: Google VP9
  ylc: YUY2 Lossless Codec
  vp4: On2 VP4
  prores: Apple ProRes (iCodec Pro)
  vmix: vMix Video
  mpeg4_cuvid: Nvidia CUVID MPEG4 decoder
  utvideo: Ut Video
  v408: Uncompressed packed QT 4:4:4:4
  av1_cuvid: Nvidia CUVID AV1 decoder
  dsicinvideo: Delphine Software International CIN video
  binkvideo: Bink video
  h264_cuvid: Nvidia CUVID H264 decoder
  vp6a: On2 VP6 (Flash version, with alpha channel)
  msmpeg4v2: MPEG-4 part 2 Microsoft variant version 2
  hdr: HDR (Radiance RGBE format) image
  alias_pix: Alias/Wavefront PIX image
  xpm: XPM (X PixMap) image
  psd: Photoshop PSD file
  tiertexseqvideo: Tiertex Limited SEQ video
  libdav1d: dav1d AV1 decoder by VideoLAN
  sga: Digital Pictures SGA Video
  dnxhd: VC3/DNxHD
  rl2: RL2 video
  cdxl: Commodore CDXL video
  mjpeg: MJPEG (Motion JPEG)
  phm: PHM (Portable HalfFloatMap) image
  png: PNG (Portable Network Graphics) image
  wrapped_avframe: AVPacket to AVFrame passthrough
  mpeg2video: MPEG-2 video
  scpr: ScreenPressor
  av1: Alliance for Open Media AV1
  mpeg2_cuvid: Nvidia CUVID MPEG2VIDEO decoder
  jpeg2000: JPEG 2000
  hymt: HuffYUV MT
  wmv2: Windows Media Video 8
  bmp: BMP (Windows and OS/2 bitmap)
  flv: FLV / Sorenson Spark / Sorenson H.263 (Flash Video)
  vvc: VVC (Versatile Video Coding)
  yuv4: Uncompressed packed 4:2:0
  exr: OpenEXR image
  yop: Psygnosis YOP Video
  dxv: Resolume DXV
  frwu: Forward Uncompressed
  huffyuv: Huffyuv / HuffYUV
  kgv1: Kega Game Video
  flashsv2: Flash Screen Video v2
  mvc1: Silicon Graphics Motion Video Compressor 1
  pgmyuv: PGMYUV (Portable GrayMap YUV) image
  libvpx-vp9: libvpx VP9
  xan_wc4: Wing Commander IV / Xxan
  bfi: Brute Force & Ignorance
  wnv1: Winnov WNV1
  ffvhuff: Huffyuv FFmpeg variant
  h263p: H.263 / H.263-1996, H.263+ / H.263-1998 / H.263 version 2
  aasc: Autodesk RLE
  h263i: Intel H.263
  indeo3: Intel Indeo 3
  dds: DirectDraw Surface image decoder
  tiff: TIFF image
  msvideo1: Microsoft Video 1
  theora: Theora
  motionpixels: Motion Pixels video
  pgm: PGM (Portable GrayMap) image
  avrn: Avid AVI Codec
  rpza: QuickTime video (RPZA)
  idf: iCEDraw text
  clearvideo: Iterated Systems ClearVideo
  rasc: RemotelyAnywhere Screen Capture
  mobiclip: MobiClip Video
  vmnc: VMware Screen Codec / VMware Video
  webp: WebP image
  mdec: Sony PlayStation MDEC (Motion DECoder)
  pixlet: Apple Pixlet
  msp2: Microsoft Paint (MSP) version 2
  txd: Renderware TXD (TeXture Dictionary) image
  gif: GIF (Graphics Interchange Format)
  mimic: Mimic
  012v: Uncompressed 4:2:2 10-bit
  mpeg4: MPEG-4 part 2
  dpx: DPX (Digital Picture Exchange) image
  bmv_video: Discworld II BMV video
  lead: LEAD MCMP
  eatqi: Electronic Arts TQI Video
  g2m: Go2Meeting
  dirac: BBC Dirac VC-2
  imm4: Infinity IMM4
  wmv3: Windows Media Video 9
  notchlc: NotchLC
  escape130: Escape 130
  mss1: MS Screen 1
  mjpegb: Apple MJPEG-B
  pgx: PGX (JPEG2000 Test Format)
  cavs: Chinese AVS (Audio Video Standard) (AVS1-P2, JiZhun profile)
  smackvid: Smacker video
  ipu: IPU Video
  fits: Flexible Image Transport System
  zmbv: Zip Motion Blocks Video
  vc1: SMPTE VC-1
  rscc: innoHeim/Rsupport Screen Capture Codec
  mmvideo: American Laser Games MM Video
  pdv: PDV (PlayDate Video)
  snow: Snow
  aic: Apple Intermediate Codec
  roqvideo: id RoQ video
  aura2: Auravision Aura 2
  fmvc: FM Screen Capture Codec
  imm5: Infinity IMM5
  fic: Mirillis FIC
  mv30: MidiVid 3.0
  v210: Uncompressed 4:2:2 10-bit
  gdv: Gremlin Digital Video
  pictor: Pictor/PC Paint
  8bps: QuickTime 8BPS video
  msrle: Microsoft RLE
  r210: Uncompressed RGB 10-bit
  rv40: RealVideo 4.0
  vp6f: On2 VP6 (Flash version)
  eacmv: Electronic Arts CMV video
  vp8_cuvid: Nvidia CUVID VP8 decoder
  vqc: ViewQuest VQC
  cri: Cintel RAW
  qpeg: Q-team QPEG
  lagarith: Lagarith lossless
  mszh: LCL (LossLess Codec Library) MSZH
  hqx: Canopus HQX
  qdraw: Apple QuickDraw
  vc1_cuvid: Nvidia CUVID VC1 decoder
  idcinvideo: id Quake II CIN video
  anm: Deluxe Paint Animation
'''