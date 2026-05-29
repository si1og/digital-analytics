<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Copy, Palette, Plus, RefreshCw, Trash2 } from '@lucide/vue'

const API_URL = import.meta.env.VITE_API_URL
const formats = ['HEX', 'sRGB', 'CIELAB', 'LCH', 'OKLCH', 'CMYK']
const STORAGE_KEY = 'palette-contrast.colors'

const colorInput = ref('#7b61ff')
const textColor = ref('')
const outputFormat = ref('HEX')
const shadeCount = ref(9)
const palettes = ref([])
const error = ref('')
const loading = ref(false)

const canSubmit = computed(() => colorInput.value.trim().length > 0 && !loading.value)

function normalizeHex(value, fallback = '#000000') {
  return /^#[0-9a-f]{6}$/i.test(value) ? value : fallback
}

onMounted(() => {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    palettes.value = Array.isArray(stored)
      ? stored.map((palette) => ({
          ...palette,
          editValue: palette.editValue || palette.value,
          shadeCount: Number(palette.shadeCount || palette.shades?.length || shadeCount.value),
        }))
      : []
  } catch {
    palettes.value = []
  }
})

watch(
  palettes,
  (value) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  },
  { deep: true },
)

async function requestAnalysis(
  value = colorInput.value,
  format = outputFormat.value,
  count = shadeCount.value,
) {
  loading.value = true
  error.value = ''

  try {
    const response = await fetch(`${API_URL}/colors/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        value,
        output_format: format,
        shade_count: Number(count),
        text_color: textColor.value.trim() || null,
      }),
    })

    if (!response.ok) {
      throw new Error('Цвет не распознан')
    }

    return await response.json()
  } finally {
    loading.value = false
  }
}

async function addColor() {
  if (!canSubmit.value) return

  try {
    const result = await requestAnalysis()
    palettes.value.unshift({
      id: crypto.randomUUID(),
      editValue: result.value,
      shadeCount: Number(shadeCount.value),
      ...result,
    })
    colorInput.value = result.hex
  } catch (err) {
    error.value = err.message
  }
}

async function refreshPalettes() {
  const next = []

  for (const palette of palettes.value) {
    const result = await requestAnalysis(palette.input, palette.output_format, palette.shadeCount)
    next.push({ ...palette, editValue: result.value, ...result })
  }

  palettes.value = next
}

async function applyTextColor(value = textColor.value) {
  textColor.value = value
  if (palettes.value.length > 0) {
    await refreshPalettes()
  }
}

async function convertPaletteFormat(palette, format) {
  if (palette.output_format === format || loading.value) return

  try {
    const result = await requestAnalysis(palette.input, format, palette.shadeCount)
    palettes.value = palettes.value.map((item) =>
      item.id === palette.id ? { ...item, editValue: result.value, ...result } : item,
    )
  } catch (err) {
    error.value = err.message
  }
}

async function updatePaletteColor(palette) {
  const value = palette.editValue.trim()
  if (!value || value === palette.value || loading.value) return

  try {
    const result = await requestAnalysis(value, palette.output_format, palette.shadeCount)
    palettes.value = palettes.value.map((item) =>
      item.id === palette.id ? { ...item, editValue: result.value, ...result } : item,
    )
  } catch (err) {
    error.value = err.message
    palettes.value = palettes.value.map((item) =>
      item.id === palette.id ? { ...item, editValue: item.value } : item,
    )
  }
}

async function updatePaletteShadeCount(palette) {
  const count = Math.max(1, Number(palette.shadeCount) || 1)

  if (count === palette.shades.length || loading.value) {
    palette.shadeCount = count
    return
  }

  try {
    const result = await requestAnalysis(palette.input, palette.output_format, count)
    palettes.value = palettes.value.map((item) =>
      item.id === palette.id ? { ...item, shadeCount: count, editValue: result.value, ...result } : item,
    )
  } catch (err) {
    error.value = err.message
    palette.shadeCount = palette.shades.length
  }
}

async function pickPaletteColor(palette, value) {
  palette.editValue = value
  await updatePaletteColor(palette)
}

function removePalette(id) {
  palettes.value = palettes.value.filter((palette) => palette.id !== id)
}

async function copyValue(value) {
  await navigator.clipboard.writeText(value)
}

function shadeTextColor(palette, shade) {
  return palette.text_color || shade.contrast.recommended_hex
}

function shadeContrastValue(shade) {
  return shade.contrast.custom ?? Math.max(shade.contrast.white, shade.contrast.black)
}
</script>

<template>
  <main class="workspace">
    <section class="toolbar" aria-label="Параметры анализа цвета">
      <div class="title-block">
        <p>Палитра контрастности</p>
        <h1>Анализ цвета, оттенков и читаемости текста</h1>
      </div>

      <form class="controls" @submit.prevent="addColor">
        <label class="field">
          <span>Цвет</span>
          <span class="color-input">
            <input v-model="colorInput" maxlength="64" placeholder="#7b61ff или lab(50 40 -70)" />
            <label class="picker-control" :style="{ '--picked-color': normalizeHex(colorInput) }">
              <Palette :size="18" />
              <input
                aria-label="Выбрать цвет"
                class="native-picker"
                type="color"
                :value="normalizeHex(colorInput)"
                @input="colorInput = $event.target.value"
              />
            </label>
          </span>
        </label>

        <label class="field compact">
          <span>Текст</span>
          <span class="color-input">
            <input
              v-model="textColor"
              maxlength="64"
              placeholder="#ffffff"
              @blur="applyTextColor()"
              @keydown.enter.prevent="applyTextColor()"
            />
            <label class="picker-control" :style="{ '--picked-color': normalizeHex(textColor, '#ffffff') }">
              <Palette :size="18" />
              <input
                aria-label="Выбрать цвет текста"
                class="native-picker"
                type="color"
                :value="normalizeHex(textColor, '#ffffff')"
                @change="applyTextColor($event.target.value)"
              />
            </label>
          </span>
        </label>

        <label class="field compact">
          <span>Оттенки</span>
          <input v-model="shadeCount" min="1" type="number" />
        </label>

        <label class="select-field">
          <span>Формат</span>
          <select v-model="outputFormat">
            <button>
              <selectedcontent></selectedcontent>
            </button>
            <option v-for="format in formats" :key="format" :value="format">{{ format }}</option>
          </select>
        </label>

        <button class="icon-button primary" :disabled="!canSubmit" title="Добавить цвет">
          <Plus :size="18" />
          <span>Добавить</span>
        </button>

        <button
          class="icon-button"
          :disabled="palettes.length === 0 || loading"
          title="Пересчитать палитры"
          type="button"
          @click="refreshPalettes"
        >
          <RefreshCw :size="18" />
        </button>
      </form>

      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section class="palette-list" aria-label="Добавленные цвета">
      <article v-if="palettes.length === 0" class="empty-state">
        <p>Добавьте цвет, чтобы увидеть конвертацию, шкалу оттенков и контраст с белым или чёрным текстом.</p>
      </article>

      <article v-for="palette in palettes" :key="palette.id" class="palette-card">
        <header class="palette-header">
          <div class="sample" :style="{ backgroundColor: palette.hex }"></div>
          <div class="editable-title">
            <p>{{ palette.output_format }}</p>
            <input
              v-model="palette.editValue"
              maxlength="64"
              :aria-label="`Значение цвета ${palette.output_format}`"
              @blur="updatePaletteColor(palette)"
              @keydown.enter.prevent="updatePaletteColor(palette)"
            />
            <label
              class="picker-control title-picker"
              :style="{ '--picked-color': normalizeHex(palette.hex) }"
            >
              <Palette :size="18" />
              <input
                class="native-picker"
                type="color"
                :aria-label="`Выбрать цвет для ${palette.hex}`"
                :value="normalizeHex(palette.hex)"
                @change="pickPaletteColor(palette, $event.target.value)"
              />
            </label>
            <span>{{ palette.hex }} · {{ palette.detected_space }}</span>
          </div>
          <div class="card-actions">
            <label class="select-field card-format">
              <span>Формат карточки</span>
              <select
                :value="palette.output_format"
                @change="convertPaletteFormat(palette, $event.target.value)"
              >
                <button>
                  <selectedcontent></selectedcontent>
                </button>
                <option v-for="format in formats" :key="format" :value="format">{{ format }}</option>
              </select>
            </label>

            <label class="field card-shades">
              <span>Оттенки</span>
              <input
                v-model="palette.shadeCount"
                min="1"
                type="number"
                @blur="updatePaletteShadeCount(palette)"
                @keydown.enter.prevent="updatePaletteShadeCount(palette)"
              />
            </label>

            <button class="tool-button" title="Удалить цвет" @click="removePalette(palette.id)">
              <Trash2 :size="18" />
            </button>
          </div>
        </header>

        <div v-if="!palette.text_color" class="metrics">
          <div>
            <span>Белый текст</span>
            <strong>{{ palette.contrast.white }}:1</strong>
          </div>
          <div>
            <span>Чёрный текст</span>
            <strong>{{ palette.contrast.black }}:1</strong>
          </div>
          <div>
            <span>Рекомендация</span>
            <strong>{{ palette.contrast.recommended === 'black' ? 'чёрный' : 'белый' }}</strong>
          </div>
        </div>
        <div v-else class="metrics custom-metrics">
          <div>
            <span>Цвет текста</span>
            <strong :style="{ color: palette.text_color }">{{ palette.text_color }}</strong>
          </div>
          <div>
            <span>Контраст</span>
            <strong>{{ palette.contrast.custom }}:1</strong>
          </div>
        </div>

        <div class="formats">
          <button
            v-for="(value, format) in palette.formats"
            :key="format"
            class="format-value"
            :title="`Скопировать ${format}`"
            @click="copyValue(value)"
          >
            <span>{{ format }}</span>
            <strong>{{ value }}</strong>
            <Copy :size="14" />
          </button>
        </div>

        <div class="shade-grid">
          <button
            v-for="shade in palette.shades"
            :key="shade.index"
            class="shade"
            :class="{ selected: shade.is_source_position }"
            :style="{ backgroundColor: shade.hex, color: shadeTextColor(palette, shade) }"
            :title="shade.value"
            @click="copyValue(shade.value)"
          >
            <span>{{ shade.index }}</span>
            <strong>{{ shade.value }}</strong>
            <small>{{ shadeContrastValue(shade) }}:1</small>
          </button>
        </div>
      </article>
    </section>
  </main>
</template>
