<template>
  <div id="app">
    <!-- Landing Page -->
    <ArchWorkspace
      v-if="currentApp === 'landing'"
      @open-app="openApp"
    />

    <!-- AA图应用 -->
    <AADiagramApp
      v-else-if="currentApp === 'aadiagram'"
      @back-to-landing="backToLanding"
    />

    <!-- 配置应用 -->
    <ConfigApp
      v-else-if="currentApp === 'config'"
      @back-to-landing="backToLanding"
    />
  </div>
</template>

<script>
import ArchWorkspace from './components/ArchWorkspace.vue'
import AADiagramApp from './views/AADiagramApp/index.vue'
import ConfigApp from './components/ConfigApp.vue'

export default {
  name: 'App',
  components: {
    ArchWorkspace,
    AADiagramApp,
    ConfigApp
  },
  data() {
    return {
      currentApp: 'landing' // landing, aadiagram, config
    }
  },
  methods: {
    openApp(appName) {
      this.currentApp = appName
    },
    backToLanding() {
      this.currentApp = 'landing'
    }
  }
}
</script>

<style lang="scss">
@import './styles/index.scss';

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  min-height: 100vh;
}
</style>
