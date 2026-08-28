/* Street Banker · SB-12 CNV-2 — the format bench.
 *
 * Anything the browser can decode goes in; exact PCM comes out. The
 * decoding is the browser's (MP3, WAV, FLAC, M4A/AAC, OGG, WebM — whatever
 * it supports), the resampling is the browser's OfflineAudioContext, and
 * the container is written here: WAV or AIFF, 16- or 24-bit integer or
 * 32-bit float, mono or stereo.
 *
 * Why only those two containers: a browser has no MP3, AAC or FLAC
 * ENCODER exposed to script. MediaRecorder can sometimes produce AAC or
 * Opus, and the panel offers those when the browser reports support — but
 * that is the browser's encoder at its own bitrate, not ours, and it is
 * labelled that way. Nothing here claims a quality it cannot deliver.
 *
 * Dither: going to 16-bit truncates 8 bits of a 24-bit master, and plain
 * truncation correlates the error with the signal, which is the quiet
 * grit people hear on bad bounces. TPDF dither at 1 LSB decorrelates it -
 * standard practice for any downward bit-depth conversion.
 *
 * Pure arrays in, ArrayBuffer out. No DOM, no network, so the headers can
 * be parsed back and checked byte for byte in Node.
 */
(function (root) {
  "use strict";

  function writeAscii(dv, offset, text) {
    for (var i = 0; i < text.length; i++) {
      dv.setUint8(offset + i, text.charCodeAt(i));
    }
  }

  function clamp(v) { return v < -1 ? -1 : (v > 1 ? 1 : v); }

  /* TPDF dither: the sum of two uniform randoms, scaled to one least
     significant bit of the target depth. Only ever applied when we are
     actually losing resolution. */
  function makeDither(bits, enabled) {
    if (!enabled || bits >= 32) { return function () { return 0; }; }
    var lsb = 1 / Math.pow(2, bits - 1);
    return function () {
      return (Math.random() + Math.random() - 1) * lsb;
    };
  }

  function peak(channels) {
    var p = 0;
    for (var c = 0; c < channels.length; c++) {
      var d = channels[c];
      for (var i = 0; i < d.length; i++) {
        var a = d[i] < 0 ? -d[i] : d[i];
        if (a > p) { p = a; }
      }
    }
    return p;
  }

  function peakDbfs(channels) {
    var p = peak(channels);
    return p > 0 ? 20 * Math.log(p) / Math.LN10 : -Infinity;
  }

  /* Interleave and quantise once; both containers share the sample maths
     and differ only in byte order and header. */
  function writeSamples(dv, offset, channels, bits, littleEndian, dither) {
    var ch = channels.length, len = channels[0].length;
    var i, c, v;
    for (i = 0; i < len; i++) {
      for (c = 0; c < ch; c++) {
        v = channels[c][i];
        if (bits === 32) {
          dv.setFloat32(offset, v, littleEndian);
          offset += 4;
          continue;
        }
        v = clamp(v + dither());
        if (bits === 16) {
          dv.setInt16(offset, Math.round(v < 0 ? v * 32768 : v * 32767),
                      littleEndian);
          offset += 2;
        } else {
          var s = Math.round(v < 0 ? v * 8388608 : v * 8388607);
          if (s > 8388607) { s = 8388607; }
          if (s < -8388608) { s = -8388608; }
          if (s < 0) { s += 16777216; }
          if (littleEndian) {
            dv.setUint8(offset, s & 255);
            dv.setUint8(offset + 1, (s >> 8) & 255);
            dv.setUint8(offset + 2, (s >> 16) & 255);
          } else {
            dv.setUint8(offset, (s >> 16) & 255);
            dv.setUint8(offset + 1, (s >> 8) & 255);
            dv.setUint8(offset + 2, s & 255);
          }
          offset += 3;
        }
      }
    }
    return offset;
  }

  function encodeWav(channels, rate, bits, opts) {
    opts = opts || {};
    bits = bits || 16;
    var ch = channels.length, len = channels[0].length;
    var bytesPer = bits / 8;
    var dataBytes = len * ch * bytesPer;
    var fmtBytes = 16;
    var ab = new ArrayBuffer(44 + dataBytes);
    var dv = new DataView(ab);
    writeAscii(dv, 0, "RIFF");
    dv.setUint32(4, 36 + dataBytes, true);
    writeAscii(dv, 8, "WAVE");
    writeAscii(dv, 12, "fmt ");
    dv.setUint32(16, fmtBytes, true);
    // 1 = integer PCM, 3 = IEEE float. Players read this, not the depth.
    dv.setUint16(20, bits === 32 ? 3 : 1, true);
    dv.setUint16(22, ch, true);
    dv.setUint32(24, rate, true);
    dv.setUint32(28, rate * ch * bytesPer, true);
    dv.setUint16(32, ch * bytesPer, true);
    dv.setUint16(34, bits, true);
    writeAscii(dv, 36, "data");
    dv.setUint32(40, dataBytes, true);
    writeSamples(dv, 44, channels, bits, true,
                 makeDither(bits, opts.dither !== false));
    return ab;
  }

  /* AIFF stores the sample rate as an 80-bit IEEE 754 extended float,
     which nothing else in web audio ever needs. Unlike a double, the
     extended format writes the leading 1 of the mantissa explicitly, so
     the 64-bit mantissa field is exactly mantissa * 2^63 - the top word
     being mantissa * 2^31. Get that wrong and every player reads the
     wrong sample rate. */
  function writeExtended(dv, offset, value) {
    var z;
    if (!value || value <= 0) {
      for (z = 0; z < 10; z++) { dv.setUint8(offset + z, 0); }
      return;
    }
    var exponent = Math.floor(Math.log(value) / Math.LN2);
    var mantissa = value / Math.pow(2, exponent);   // 1 <= mantissa < 2
    if (mantissa >= 2) { mantissa /= 2; exponent += 1; }
    dv.setUint16(offset, 16383 + exponent, false);  // sign 0, biased exp
    var top = mantissa * Math.pow(2, 31);
    var hi = Math.floor(top);
    var lo = Math.round((top - hi) * Math.pow(2, 32));
    if (lo >= 4294967296) { lo = 0; hi += 1; }      // carry, never overflow
    dv.setUint32(offset + 2, hi, false);
    dv.setUint32(offset + 6, lo, false);
  }

  function encodeAiff(channels, rate, bits, opts) {
    opts = opts || {};
    bits = bits || 16;
    if (bits === 32) { bits = 24; }   // plain AIFF has no float flavour
    var ch = channels.length, len = channels[0].length;
    var bytesPer = bits / 8;
    var dataBytes = len * ch * bytesPer;
    var ssndBytes = 8 + dataBytes;    // offset + blockSize + samples
    var ab = new ArrayBuffer(12 + 8 + 18 + 8 + ssndBytes);
    var dv = new DataView(ab);
    writeAscii(dv, 0, "FORM");
    dv.setUint32(4, ab.byteLength - 8, false);
    writeAscii(dv, 8, "AIFF");
    writeAscii(dv, 12, "COMM");
    dv.setUint32(16, 18, false);
    dv.setUint16(20, ch, false);
    dv.setUint32(22, len, false);
    dv.setUint16(26, bits, false);
    writeExtended(dv, 28, rate);
    writeAscii(dv, 38, "SSND");
    dv.setUint32(42, ssndBytes, false);
    dv.setUint32(46, 0, false);       // offset
    dv.setUint32(50, 0, false);       // blockSize
    writeSamples(dv, 54, channels, bits, false,
                 makeDither(bits, opts.dither !== false));
    return ab;
  }

  var FORMATS = {
    wav: {label: "WAV", ext: "wav", mime: "audio/wav",
          depths: [16, 24, 32], encode: encodeWav},
    aiff: {label: "AIFF", ext: "aiff", mime: "audio/aiff",
           depths: [16, 24], encode: encodeAiff},
  };

  /* Which lossy targets this browser will actually encode. Feature-probed
     rather than assumed, because MediaRecorder support for AAC in
     particular varies by platform even within one browser. */
  function browserCodecs() {
    var out = [];
    if (typeof MediaRecorder === "undefined"
        || !MediaRecorder.isTypeSupported) { return out; }
    [["audio/mp4", "M4A / AAC", "m4a"],
     ["audio/webm;codecs=opus", "WebM / Opus", "webm"],
     ["audio/ogg;codecs=opus", "OGG / Opus", "ogg"]]
      .forEach(function (spec) {
        if (MediaRecorder.isTypeSupported(spec[0])) {
          out.push({mime: spec[0], label: spec[1], ext: spec[2]});
        }
      });
    return out;
  }

  function encode(format, channels, rate, bits, opts) {
    var spec = FORMATS[format];
    if (!spec) { throw new Error("unknown format: " + format); }
    return spec.encode(channels, rate, bits, opts);
  }

  var api = {
    encodeWav: encodeWav,
    encodeAiff: encodeAiff,
    encode: encode,
    peak: peak,
    peakDbfs: peakDbfs,
    browserCodecs: browserCodecs,
    FORMATS: FORMATS,
    RATES: [22050, 32000, 44100, 48000, 88200, 96000],
    _writeExtended: writeExtended,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.SBAudioConv = api;
})(typeof self !== "undefined" ? self : this);
