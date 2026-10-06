import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Field } from '../../components/Field'

type Detector = { detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]> }
const FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e']

/** Chrome on Android has a native detector; elsewhere load the self-hosted ZXing wasm on demand. */
async function createDetector(): Promise<Detector> {
  const native = (globalThis as { BarcodeDetector?: new (o: { formats: string[] }) => Detector })
    .BarcodeDetector
  if (native) return new native({ formats: FORMATS })
  const [{ BarcodeDetector, prepareZXingModule }, wasm] = await Promise.all([
    import('barcode-detector/ponyfill'),
    import('zxing-wasm/reader/zxing_reader.wasm?url'),
  ])
  prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) =>
        path.endsWith('.wasm') ? wasm.default : prefix + path,
    },
  })
  return new BarcodeDetector({ formats: FORMATS as never })
}

/** Camera scanning with a typed fallback. Calls onCode once per detected code. */
export function Scanner({ onCode }: { onCode: (code: string) => void }) {
  const { t } = useTranslation()
  const video = useRef<HTMLVideoElement>(null)
  const [typed, setTyped] = useState('')
  const [camera, setCamera] = useState<'starting' | 'on' | 'unavailable'>('starting')

  useEffect(() => {
    let stream: MediaStream | null = null
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    async function start() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('no camera')
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
          audio: false,
        })
        if (stopped || !video.current) return
        video.current.srcObject = stream
        await video.current.play()
        const detector = await createDetector()
        setCamera('on')
        const tick = async () => {
          if (stopped || !video.current) return
          try {
            const [hit] = await detector.detect(video.current)
            if (hit?.rawValue) {
              stopped = true
              onCode(hit.rawValue)
              return
            }
          } catch {
            // a frame that cannot be read yet; try the next one
          }
          timer = setTimeout(() => void tick(), 200)
        }
        void tick()
      } catch {
        setCamera('unavailable')
      }
    }
    void start()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [onCode])

  return (
    <div className="stack scanner">
      {camera !== 'unavailable' ? (
        <video ref={video} className="camera" muted playsInline aria-label={t('scan.camera')} />
      ) : (
        <p className="muted">{t('scan.noCamera')}</p>
      )}
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault()
          if (typed.trim()) onCode(typed.trim())
        }}
      >
        <Field
          label={t('scan.typeCode')}
          inputMode="numeric"
          autoComplete="off"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <button type="submit">{t('scan.lookUp')}</button>
      </form>
    </div>
  )
}
