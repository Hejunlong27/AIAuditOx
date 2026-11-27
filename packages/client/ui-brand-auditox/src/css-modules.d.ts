declare module '*.module.css' {
  const classes: Record<string, string>
  export default classes
}

declare module '*.css?inline' {
  const text: string
  export default text
}
