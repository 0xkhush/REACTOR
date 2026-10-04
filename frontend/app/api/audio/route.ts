import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const folder = searchParams.get('folder')
  const stream = searchParams.get('stream') || 'input' // 'input' or 'output'

  if (!folder || folder.includes('..') || folder.includes('/') || folder.includes('\\')) {
    return new NextResponse('Invalid folder parameter', { status: 400 })
  }

  // Repository root is the parent directory of reactor-frontend-design
  const repoRoot = path.resolve(process.cwd(), '..')
  let filePath = ''

  if (stream === 'input') {
    filePath = path.join(repoRoot, 'fdb_v3_data_released', folder, 'input.wav')
  } else {
    filePath = path.join(repoRoot, 'artifacts', 'batch_inference', folder, 'output.wav')
  }

  // Fallback: check within current working directory if running from repo root
  if (!fs.existsSync(filePath)) {
    if (stream === 'input') {
      filePath = path.join(process.cwd(), 'fdb_v3_data_released', folder, 'input.wav')
    } else {
      filePath = path.join(process.cwd(), 'artifacts', 'batch_inference', folder, 'output.wav')
    }
  }

  if (!fs.existsSync(filePath)) {
    return new NextResponse(`Audio file not found: ${filePath}`, { status: 404 })
  }

  const stat = fs.statSync(filePath)
  const fileSize = stat.size
  const range = req.headers.get('range')

  if (range) {
    const parts = range.replace(/bytes=/, '').split('-')
    const start = parseInt(parts[0], 10)
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1
    const chunkSize = end - start + 1
    const fileStream = fs.createReadStream(filePath, { start, end })

    const webStream = new ReadableStream({
      start(controller) {
        fileStream.on('data', chunk => controller.enqueue(chunk))
        fileStream.on('end', () => controller.close())
        fileStream.on('error', err => controller.error(err))
      },
    })

    return new NextResponse(webStream, {
      status: 206,
      headers: {
        'Content-Range': `bytes ${start}-${end}/${fileSize}`,
        'Accept-Ranges': 'bytes',
        'Content-Length': chunkSize.toString(),
        'Content-Type': 'audio/wav',
      },
    })
  } else {
    const fileStream = fs.createReadStream(filePath)
    const webStream = new ReadableStream({
      start(controller) {
        fileStream.on('data', chunk => controller.enqueue(chunk))
        fileStream.on('end', () => controller.close())
        fileStream.on('error', err => controller.error(err))
      },
    })

    return new NextResponse(webStream, {
      status: 200,
      headers: {
        'Content-Length': fileSize.toString(),
        'Content-Type': 'audio/wav',
        'Accept-Ranges': 'bytes',
      },
    })
  }
}
